# Smart Safety Mining - Backend Documentation

This document provides a comprehensive overview of the backend architecture, the system's operational flow, and the available REST API endpoints for the Smart Safety Mining platform.

---

## 1. System Architecture

The backend is built using **Django** and the **Django REST Framework (DRF)**. It is divided into two primary applications:
1. **AuthUser**: Handles custom user management, roles, and JWT-based authentication.
2. **Analytics**: Handles core business logic, IoT data ingestion, AI risk prediction, geofencing, and incident reporting.

### Architecture Diagram

```mermaid
graph TD
  subgraph "User Interaction (HTTP)"
    Client[Frontend Web App / Mobile]
    Router[Django URL Router]
    AuthViews[Authentication Views]
    AnalyticsViews[Admin ViewSets <br/> (Zones, Incidents, etc.)]
    
    Client -->|HTTP/JSON| Router
    Router -->|/auth/*| AuthViews
    Router -->|/api/*| AnalyticsViews
    AnalyticsViews --> DB
    AuthViews --> DB
  end

  subgraph "Real-Time IoT Pipeline"
    IoT[IoT Sensor Devices]
    Redis[(Redis <br/> Cache & Broker)]
    Celery[Celery Worker <br/> (process_iot_sensor_data)]
    Channels[WebSocket Layer <br/> (Daphne/Channels)]
    
    subgraph "Celery Task Logic"
        AIService[AI Risk Predictor]
        GeofenceService[Geofencing Service]
    end

    IoT -->|LPUSH data| Redis
    Celery -->|Pulls data from| Redis
    Celery --> AIService
    Celery --> GeofenceService
    Celery -->|Saves results to| DB[(Relational DB)]
    
    Celery -->|Broadcasts via| Redis
    Redis -->|Pub/Sub| Channels
    Channels -->|Streams data to| Client
  end
```

---

## 2. How the Backend System Works

### 2.1. Authentication & Authorization
* **JWT Tokens:** The system uses JSON Web Tokens (JWT) for stateless authentication. When a user logs in via `/auth/login/`, they receive an `access` token and a `refresh` token.
* **Role-Based Access Control (RBAC):** The `CustomUser` model includes a `role` field (Admin, Manager, Safety Officer, Worker). Custom permission classes (e.g., `IsSafetyOfficerRole`) restrict endpoint access depending on the user's role. For example, only Safety Officers and Admins can create or modify geofenced `Zones`.

### 2.2. IoT Data Ingestion & Real-Time Processing
When a wearable device sends data to the `/api/sensor-events/` endpoint, a specialized workflow triggers:
1. **Serialization:** The incoming JSON payload is validated against the `SensorEventSerializer`.
2. **Database Save:** The raw `SensorEvent` is saved to the database.
3. **AI Risk Prediction:** The `predict_risk_level()` function uses a trained **Decision Tree Classifier** to analyze environmental and biometric data (gas, temperature, heart rate, fall detection). It returns a risk level (Safe, Warning, Danger).
4. **Geofencing Check:** Using the `Shapely` library, the system checks if the worker's triangulated `(x, y)` coordinates fall inside any configured polygon `Zones`.
5. **Status Update & Alerting:** The worker's `WorkerStatus` is instantly updated. If the AI detects danger or the worker breaches an unsafe zone, an `Alert` is automatically generated in the database.

### 2.3. Incident and Analytics Reporting
* **Incidents:** Workers and supervisors can manually report incidents, which can be linked to automated alerts.
* **Analytics:** Dedicated endpoints generate aggregate data summaries (e.g., count of alerts by severity) and provide CSV exports for compliance and auditing.

---

## 3. API URL Endpoints

Base URL: `http://localhost:8000` (or production domain)

### 3.1. Authentication Endpoints (`/auth/`)

| HTTP Method | Endpoint | Description | Access / Roles |
| :--- | :--- | :--- | :--- |
| `POST` | `/auth/register/` | Register a new user | Authenticated Users |
| `POST` | `/auth/login/` | Login and receive JWT tokens | Public |
| `POST` | `/auth/logout/` | Blacklist the refresh token | Authenticated Users |
| `POST` | `/auth/token/refresh/` | Obtain a new access token | Public (Requires Refresh Token) |
| `GET` | `/auth/user/profile/` | Get current user's profile | Authenticated Users |
| `PUT` | `/auth/user/update/` | Update current user's profile | Authenticated Users |
| `DELETE` | `/auth/user/delete/` | Delete current user's account | Authenticated Users |
| `GET` | `/auth/user/list/` | List all system users | Admin, Manager, Officer |
| `GET` | `/auth/user/<id>/` | Get details of a specific user | Admin, Manager, Officer |

### 3.2. Core Analytics Endpoints (`/api/`)

These endpoints are automatically generated via DRF ViewSets and Routers. 
*Note: `<id>` refers to the primary key of the resource.*

#### Zones (Geofencing)
| HTTP Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/zones/` | List all defined zones |
| `POST` | `/api/zones/` | Create a new zone |
| `GET, PUT, DELETE`| `/api/zones/<id>/` | View, update, or delete a zone |

#### Sensor Events (IoT Data)
| HTTP Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/sensor-events/` | List historical sensor events |
| `POST` | `/api/sensor-events/` | Ingest new sensor data (Triggers AI/Geofencing) |
| `GET, PUT, DELETE`| `/api/sensor-events/<id>/` | View, update, or delete an event |

#### Worker Status (Real-time tracking)
| HTTP Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/worker-statuses/` | View current status of all workers |
| `GET, PUT, DELETE`| `/api/worker-statuses/<id>/` | View, update, or delete a status |

#### Alerts (System Generated)
| HTTP Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/alerts/` | List all system alerts |
| `GET, PUT, DELETE`| `/api/alerts/<id>/` | View, update, or delete an alert |

#### Incidents (Manually Reported)
| HTTP Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/incidents/` | List all reported incidents |
| `POST` | `/api/incidents/` | Report a new incident |
| `GET, PUT, DELETE`| `/api/incidents/<id>/` | View, update, or delete an incident |

#### Analytics (Custom Actions)
| HTTP Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/analytics/summary/` | Retrieve a JSON summary of safety metrics |
| `GET` | `/api/analytics/export_csv/`| Download a CSV export of the alert history |