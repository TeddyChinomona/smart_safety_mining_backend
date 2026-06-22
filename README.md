# Smart Safety Mining — Backend

A real-time worker safety monitoring platform for underground mining operations. The backend ingests IoT sensor data from BLE wearables and GPS devices, runs AI risk prediction, evaluates geofence boundaries, and streams live updates to connected dashboards via WebSocket.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | Django 6 + Django REST Framework |
| ASGI server | Daphne 4 |
| Real-time | Django Channels 4 + Redis channel layer |
| Task queue | Celery 5 + Celery Beat |
| Message broker | Redis (Alpine) |
| Database | SQLite (named Docker volume) |
| Geofencing | Shapely 2 |
| AI / ML | scikit-learn `DecisionTreeClassifier` |
| Authentication | JWT via `djangorestframework-simplejwt` |
| Containerisation | Docker Compose |

---

## Architecture

```
IoT Devices
  ├── Device 1 (GPS sensors)  ──LPUSH──► Redis: gps_sensor_data
  └── Device 2 (BLE wearables)──LPUSH──► Redis: iot_sensor_data
                                                │
                                         Celery Beat (scheduler)
                                           ├── process_gps_sensor_data  (every 3 s)
                                           │     ├── Upsert GPSSensor record
                                           │     ├── Log GPSSensorReading
                                           │     ├── Recompute Zone convex hull (Shapely)
                                           │     └── Broadcast Zone via WebSocket
                                           └── process_iot_sensor_data  (every 5 s)
                                                 ├── AI risk prediction (Decision Tree)
                                                 ├── BLE geofencing (Shapely)
                                                 ├── Update WorkerStatus + generate Alerts
                                                 └── Broadcast SensorEvent + WorkerStatus via WebSocket
                                                                │
                                                      Django Channels (Daphne)
                                                        ├── ws/sensor-events/
                                                        ├── ws/worker-statuses/
                                                        └── ws/zone-updates/
```

### Dual-device positioning model

- **Device 1 — GPS sensors** are fixed reference points distributed across the mine. Their readings accumulate and are used to compute a convex hull polygon that defines a `Zone`'s geofence boundary.
- **Device 2 — BLE wearables** carried by workers scan for the nearest GPS beacon and report its `sensor_id` plus a BLE distance estimate. The worker's approximate position is inferred from that GPS sensor's last known fix.

---

## Project Structure

```
smart_safety_mining/          ← Django project package
├── settings.py
├── urls.py
├── asgi.py                   ← Channels ProtocolTypeRouter
├── celery.py

Analytics/                    ← Core business logic app
├── models.py                 ← Zone, MiningSession, GPSSensor, SensorEvent, WorkerStatus, Alert, Incident
├── views.py                  ← DRF ViewSets
├── serializers.py
├── tasks.py                  ← Celery tasks (GPS + BLE pipelines)
├── consumers.py              ← WebSocket consumers
├── ai_services.py            ← Decision Tree risk predictor
├── routing.py                ← WebSocket URL patterns
└── urls.py

AuthUser/                     ← Custom user / auth app
├── models.py                 ← CustomUser (AbstractUser + role field)
├── views.py
├── serializers.py
├── permissions.py            ← IsAdminRole, IsManagerRole, IsSafetyOfficerRole, IsWorkerRole
└── urls.py

docker-compose.yaml
Dockerfile
requirements.txt
manage.py
setup_demo.py                 ← Idempotent bootstrap script (admin user + Redis queue flush)
simulate_gps.py               ← Device 1 simulator
simulate_iot.py               ← Device 2 simulator
run_simulators.py             ← Docker orchestrator for both simulators
```

---

## Quick Start (Docker Compose)

### Prerequisites

- Docker Desktop (or Docker Engine + Compose plugin)

### Run

```bash
docker compose up --build
```

That single command:

1. Starts Redis
2. Builds the Python image (Alpine + all pip dependencies)
3. Runs `python manage.py migrate`
4. Runs `setup_demo.py` — creates the admin user and flushes stale Redis simulation queues
5. Starts Daphne on port 8000
6. Starts the Celery worker and Celery Beat scheduler
7. Waits 90 s for the API to be healthy, then launches both IoT simulators

The Django admin panel is available at `http://localhost:8000/admin/` once the `web` service passes its healthcheck.

### Stop

```bash
docker compose down
```

Add `-v` to also remove the named SQLite volume (full reset):

```bash
docker compose down -v
```

---

## Environment Variables

All variables are set in `docker-compose.yaml`. Override them there or pass them via `docker compose --env-file`.

### `web` service

| Variable | Default | Description |
|---|---|---|
| `DJANGO_ADMIN_USERNAME` | `admin` | Admin account username |
| `DJANGO_ADMIN_PASSWORD` | `admin123` | Admin account password |
| `DJANGO_ADMIN_EMAIL` | `admin@mine.test` | Admin account email |

### `simulator` service

| Variable | Default | Description |
|---|---|---|
| `ADMIN_USERNAME` | `admin` | API login for simulator |
| `ADMIN_PASSWORD` | `admin123` | API password for simulator |
| `API_BASE` | `http://web:8000` | Django base URL (uses Compose service name) |
| `REDIS_HOST` | `redis` | Redis hostname (uses Compose service name) |
| `REDIS_PORT` | `6379` | Redis port |
| `ZONE_NAME` | `Simba Shaft A` | Zone created on first run |
| `SESSION_NAME` | `Morning Shift` | Mining session created on first run |
| `GPS_SENSOR_IDS` | `GPS-001 GPS-002 GPS-003` | Space-separated GPS device IDs |
| `STARTUP_MAX` | `90` | Seconds to wait for API readiness |
| `GPS_WARMUP` | `20` | Seconds GPS simulator runs before BLE starts |

> **Important — Docker networking:** Inside a Compose network, `127.0.0.1` always resolves to the container itself, not a sibling service. Use the service name (`redis`, `web`) as the hostname.

---

## Services

| Container | Command | Purpose |
|---|---|---|
| `redis` | `redis:alpine` | Message broker, Celery result backend, channel layer |
| `django_app` | `daphne -b 0.0.0.0 -p 8000 ...` | HTTP + WebSocket server |
| `celery_worker` | `celery -A smart_safety_mining worker` | Processes GPS and BLE Celery tasks |
| `celery_beat` | `celery -A smart_safety_mining beat` | Schedules periodic tasks |
| `simulator` | `python run_simulators.py` | Pushes synthetic IoT data to Redis queues |

All services share the `mining_net` bridge network. The SQLite database lives in the `db_data` named volume mounted at `/data/db.sqlite3`, shared between `web`, `celery`, and `celery-beat`.

---

## API Reference

Base URL: `http://localhost:8000`

### Authentication  `/auth/`

| Method | Endpoint | Access | Description |
|---|---|---|---|
| `POST` | `/auth/login/` | Public | Returns `access` + `refresh` JWT tokens |
| `POST` | `/auth/register/` | Authenticated | Register a new user |
| `POST` | `/auth/logout/` | Authenticated | Blacklists the refresh token |
| `POST` | `/auth/token/refresh/` | Public | Exchange refresh token for new access token |
| `GET` | `/auth/user/profile/` | Authenticated | Current user profile |
| `PUT` | `/auth/user/update/` | Authenticated | Update current user profile |
| `DELETE` | `/auth/user/delete/` | Authenticated | Delete current user account |
| `GET` | `/auth/worker/list/` | Authenticated | List users with `role=worker` only |
| `GET` | `/auth/user/list/` | Admin, Manager, Officer | List all system users |
| `GET` | `/auth/user/<id>/` | Admin, Manager, Officer | Retrieve a specific user |

### Zones  `/api/zones/`

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/zones/` | List all zones |
| `POST` | `/api/zones/` | Create a zone *(Admin / Officer only)* |
| `GET` | `/api/zones/<id>/` | Retrieve a zone |
| `PUT / PATCH` | `/api/zones/<id>/` | Update a zone *(Admin / Officer only)* |
| `DELETE` | `/api/zones/<id>/` | Delete a zone *(Admin / Officer only)* |

Zone coordinates (`[[lon, lat], ...]`) are automatically recomputed by the GPS Celery task and should not be set manually in production.

### Mining Sessions  `/api/mining-sessions/`

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/mining-sessions/` | List all sessions |
| `POST` | `/api/mining-sessions/` | Start a new session *(Admin / Manager / Officer)* |
| `GET` | `/api/mining-sessions/active/` | List currently active sessions |
| `POST` | `/api/mining-sessions/<id>/end/` | Complete a session; deactivates its GPS sensors |

### GPS Sensors  `/api/gps-sensors/`

| Method | Endpoint | Description |
|---|---|---|
| `GET / POST / PUT / DELETE` | `/api/gps-sensors/` | CRUD for GPS sensor records *(Admin / Manager / Officer)* |

Sensors are auto-registered in the database on first GPS reading via `get_or_create`.

### Sensor Events  `/api/sensor-events/`

BLE wearable events are ingested through the Redis → Celery pipeline, not via HTTP POST. The HTTP endpoints are restricted to admin-level update and delete operations only.

### Worker Statuses  `/api/worker-statuses/`

Worker status is delivered in real time via WebSocket. HTTP writes (create, update, delete) are available to authenticated users.

### Alerts  `/api/alerts/`

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/alerts/` | List all alerts |
| `PATCH` | `/api/alerts/<id>/` | Update alert status (`new` → `acknowledged` → `resolved`) |
| `DELETE` | `/api/alerts/<id>/` | Delete an alert |

### Incidents  `/api/incidents/`

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/incidents/` | List all incidents |
| `POST` | `/api/incidents/` | File a new incident report |
| `PATCH` | `/api/incidents/<id>/` | Update incident status |
| `DELETE` | `/api/incidents/<id>/` | Delete an incident |

### Analytics  `/api/analytics/`

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/analytics/summary/` | JSON summary: total alerts, open incidents, active sessions, severity breakdown |
| `GET` | `/api/analytics/export_csv/` | Download alert history as `safety_report.csv` |

---

## WebSocket Endpoints

All WebSocket endpoints require a valid JWT access token passed as a query parameter:

```
ws://localhost:8000/ws/sensor-events/?token=<access_token>
ws://localhost:8000/ws/worker-statuses/?token=<access_token>
ws://localhost:8000/ws/zone-updates/?token=<access_token>
```

| Endpoint | Initial message | Live message | Description |
|---|---|---|---|
| `ws/sensor-events/` | `{ type: "initial_data", data: [...] }` | `{ type: "new_event", data: {...} }` | Last 50 BLE sensor events; live updates as new events arrive |
| `ws/worker-statuses/` | `{ type: "initial_data", data: [...] }` | `{ type: "status_update", data: {...} }` | Current status of all workers; updates after each Celery task cycle |
| `ws/zone-updates/` | `{ type: "initial_data", data: [...] }` | `{ type: "zone_update", data: {...} }` | All zone records; updates as GPS task recomputes the geofence hull |

Connections are rejected with code `4001` if the token is missing or invalid.

---

## Celery Tasks

Defined in `Analytics/tasks.py` and scheduled in `settings.CELERY_BEAT_SCHEDULE`.

### `process_gps_sensor_data` — every 3 seconds

Drains up to 50 messages from the `gps_sensor_data` Redis queue.

For each reading:
1. Resolves or creates the `GPSSensor` record (`get_or_create` by `sensor_id`)
2. Appends a `GPSSensorReading` log entry
3. Recomputes `Zone.coordinates` using Shapely's convex hull of all readings for the active session
4. Broadcasts the updated `Zone` to the `zone_updates` WebSocket group

Requires at least 3 non-collinear GPS readings before a valid polygon can be computed.

### `process_iot_sensor_data` — every 5 seconds

Drains up to 50 messages from the `iot_sensor_data` Redis queue.

For each reading:
1. Resolves the nearest GPS sensor from `nearest_gps_sensor_id`; inherits its session
2. Persists a `SensorEvent`
3. **AI risk prediction**: feeds `[gas, temp, humidity, heart_rate, fall_detected]` into the Decision Tree — returns `0` (safe), `1` (warning), or `2` (danger); creates an `Alert` if risk > 0
4. **BLE geofencing**: uses the GPS sensor's last known fix as the worker's approximate position; checks it against non-safe zone polygons using Shapely; creates an `Alert` with severity scaled by `distance_from_sensor`
5. Updates `WorkerStatus`
6. Broadcasts `SensorEvent` and `WorkerStatus` to their respective WebSocket groups

---

## User Roles

| Role | Description |
|---|---|
| `worker` | Wears the device; appears on Workers page; cannot access admin endpoints |
| `safety_officer` | Monitor hazards, manage zones and sessions |
| `manager` | Review reports, manage sessions |
| `admin` | Full access including Django admin panel |

Permission combining uses the DRF class-level `|` operator — `(ClassA | ClassB)()` — not instance-level, which would raise `TypeError`.

---

## Simulators

Three standalone scripts simulate hardware devices during development and demos. They run automatically inside the `simulator` container but can also be run locally.

### `simulate_gps.py`

Pushes GPS arc coordinates for 3 sensors to the `gps_sensor_data` Redis queue. Automatically creates a Zone and MiningSession if none are active.

### `simulate_iot.py`

Pushes BLE wearable payloads (gas, temperature, humidity, heart rate, fall detection, helmet status) to the `iot_sensor_data` Redis queue. Discovers active GPS sensor IDs from the API; creates 5 test worker accounts if the database is empty.

### `run_simulators.py`

Orchestrator used in Docker. Waits for the Django API to be healthy, starts the GPS simulator, waits `GPS_WARMUP` seconds for sensors to register in the DB, then starts the BLE simulator.

**Running simulators locally:**

```bash
pip install redis requests

# Terminal 1 — GPS sensors
ADMIN_USERNAME=admin ADMIN_PASSWORD=admin123 python simulate_gps.py

# Terminal 2 — BLE wearables
ADMIN_USERNAME=admin ADMIN_PASSWORD=admin123 python simulate_iot.py
```

---

## Database

SQLite is used for portability and ease of demo setup. The database file lives at `/data/db.sqlite3` inside a named Docker volume (`db_data`), shared by all backend containers.

The `web` container runs `python manage.py migrate` on every startup, making the setup idempotent.

### Key design notes

- **`setup_demo.py`** is a flat script in the project root (not a management command) to avoid the `management/commands/` directory placement pitfall. It also flushes the `gps_sensor_data` and `iot_sensor_data` Redis queues on every `web` container restart to discard stale payloads that reference IDs from a previous database generation.
- **RedisChannelLayer** is configured with `socket_timeout: None` to prevent idle pub/sub connection timeouts in the Celery worker process.
- **`CELERY_BROKER_URL`** and **`CELERY_RESULT_BACKEND`** use Redis db 0 and db 1 respectively to avoid key collisions with the channel layer.
