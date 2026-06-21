#!/usr/bin/env python3
"""
Smart Safety Mining — BLE wearable (Device 2) simulator.

Runs in two modes:
  Interactive  — run directly from a terminal; prompts for credentials.
  Docker/CI    — all config via environment variables; no prompts shown.

On startup this script:
  1. Logs in to the Django REST API.
  2. Fetches existing worker accounts; creates 5 test workers if none found.
  3. Fetches active GPS sensor IDs from the database so BLE payloads reference
     sensors already known to the geofencing service.
  4. Pushes BLE wearable payloads to the Redis 'iot_sensor_data' queue.

Environment variables
─────────────────────
  ADMIN_USERNAME    API login username       (default: prompt)
  ADMIN_PASSWORD    API login password       (default: prompt)
  API_BASE          Django base URL          (default: http://127.0.0.1:8000)
  REDIS_HOST        Redis hostname           (default: 127.0.0.1)
  REDIS_PORT        Redis port               (default: 6379)
  GPS_SENSOR_IDS    Space-separated fallback IDs if none registered yet
                     (default: prompt / GPS-001 GPS-002 GPS-003)

Requirements: pip install redis requests
"""

import json
import math
import os
import random
import sys
import time

try:
    import redis
    import requests
except ImportError:
    print("Install dependencies first:  pip install redis requests")
    sys.exit(1)

# ─── Config from env (Docker) or defaults ─────────────────────────────────────
API_BASE   = os.getenv("API_BASE",   "http://127.0.0.1:8000")
REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
QUEUE      = "iot_sensor_data"

_non_interactive = bool(os.getenv("ADMIN_USERNAME"))   # True = Docker mode

# Default test worker accounts created when the DB has no workers yet.
TEST_WORKERS = [
    {"username": "alice_m",   "email": "alice@mine.test",   "password": "Worker123!", "role": "worker"},
    {"username": "bob_m",     "email": "bob@mine.test",     "password": "Worker123!", "role": "worker"},
    {"username": "charlie_m", "email": "charlie@mine.test", "password": "Worker123!", "role": "worker"},
    {"username": "diana_m",   "email": "diana@mine.test",   "password": "Worker123!", "role": "worker"},
    {"username": "evan_m",    "email": "evan@mine.test",    "password": "Worker123!", "role": "worker"},
]

# ─── Redis ─────────────────────────────────────────────────────────────────────
rc = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
try:
    rc.ping()
    print("✓ Redis connected")
except redis.ConnectionError:
    print(f"✗ Cannot reach Redis on {REDIS_HOST}:{REDIS_PORT}")
    sys.exit(1)

# ─── Prompt helper ────────────────────────────────────────────────────────────
def _ask(env_key: str, prompt: str, default: str = "") -> str:
    """Return env var if set, otherwise prompt the user."""
    val = os.getenv(env_key, "")
    if val:
        return val
    if _non_interactive:
        return default
    answer = input(f"  {prompt}").strip()
    return answer or default

# ─── API helpers ───────────────────────────────────────────────────────────────
def _h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def api_login(username, password):
    r = requests.post(f"{API_BASE}/auth/login/",
                      json={"username": username, "password": password}, timeout=10)
    if r.status_code != 200:
        print(f"✗ Login failed ({r.status_code}): {r.text}")
        sys.exit(1)
    print("✓ Authenticated")
    return r.json()["access"]

def get_workers(token):
    """GET /auth/worker/list/ — only role='worker' accounts."""
    r = requests.get(f"{API_BASE}/auth/worker/list/", headers=_h(token), timeout=10)
    return r.json() if r.ok else []

def register_user(token, data):
    """POST /auth/register/ — returns False (silently) if user already exists."""
    r = requests.post(f"{API_BASE}/auth/register/", json=data, headers=_h(token), timeout=10)
    return r.ok

def get_gps_sensors(token):
    """GET /api/gps-sensors/ — requires admin/manager/officer token."""
    r = requests.get(f"{API_BASE}/api/gps-sensors/", headers=_h(token), timeout=10)
    return r.json() if r.ok else []

# ─── Banner ────────────────────────────────────────────────────────────────────
print()
print("╔══════════════════════════════════════════════════════════════╗")
print("║   Smart Safety Mining — BLE Wearable Simulator (Device 2)   ║")
print("╚══════════════════════════════════════════════════════════════╝")
print(f"  API   → {API_BASE}")
print(f"  Redis → {REDIS_HOST}:{REDIS_PORT}  queue={QUEUE}")
if _non_interactive:
    print("  Mode  → non-interactive (reading config from environment)")
print()

# ─── Credentials ──────────────────────────────────────────────────────────────
if not _non_interactive:
    print("Admin / Safety-Officer credentials")
admin_user = _ask("ADMIN_USERNAME", "Username [admin]: ", "admin")
admin_pass = _ask("ADMIN_PASSWORD", "Password: ",         "")
if not admin_pass:
    print("✗ Password required.  Set ADMIN_PASSWORD or enter it interactively.")
    sys.exit(1)
print()

token = api_login(admin_user, admin_pass)

# ─── Worker accounts ────────────────────────────────────────────────────────────
workers = get_workers(token)
if workers:
    print(f"✓ Found {len(workers)} existing worker account(s)")
else:
    print("No workers found — creating 5 test accounts…")
    for wd in TEST_WORKERS:
        created = register_user(token, wd)
        tag = "✓ created" if created else "  (skipped — already exists)"
        print(f"  {tag}: {wd['username']}")
    workers = get_workers(token)
    if not workers:
        print("✗ Worker accounts could not be created or fetched. Check API.")
        sys.exit(1)
    print(f"  → {len(workers)} worker(s) ready")

WORKER_IDS = [w["id"] for w in workers]
print(f"  Worker IDs : {WORKER_IDS}")

# ─── Discover active GPS sensors ────────────────────────────────────────────────
print()
gps_sensors = get_gps_sensors(token)
active = [g for g in gps_sensors if g.get("is_active")]

if active:
    GPS_SENSOR_IDS = [g["sensor_id"] for g in active]
    print(f"✓ Found {len(active)} active GPS sensor(s): {GPS_SENSOR_IDS}")
else:
    raw_ids = _ask("GPS_SENSOR_IDS",
                   "GPS Sensor IDs [GPS-001 GPS-002 GPS-003]: ",
                   "GPS-001 GPS-002 GPS-003")
    GPS_SENSOR_IDS = raw_ids.split()
    print("⚠  No active GPS sensors in the database yet.")
    print(f"   Continuing with fallback IDs: {GPS_SENSOR_IDS}")
    print("   (AI prediction still works; geofencing activates once GPS data arrives)")

print()
print("─" * 64)
print(f"  Workers    : {WORKER_IDS}")
print(f"  GPS sensors: {GPS_SENSOR_IDS}")
print("─" * 64)

# ─── Scenario templates ────────────────────────────────────────────────────────
TEMPLATES = {
    "safe":      dict(gas=0.4,  temp=24.0, hum=48, hr=74,  fall=False, helmet=True),
    "warning_g": dict(gas=5.5,  temp=31.0, hum=57, hr=102, fall=False, helmet=True),
    "warning_t": dict(gas=2.0,  temp=38.0, hum=61, hr=111, fall=False, helmet=True),
    "danger":    dict(gas=11.0, temp=46.0, hum=66, hr=133, fall=False, helmet=False),
    "fall":      dict(gas=0.3,  temp=25.0, hum=50, hr=144, fall=True,  helmet=True),
    "no_helmet": dict(gas=1.0,  temp=27.0, hum=52, hr=79,  fall=False, helmet=False),
}

SCHEDULE = (
    ["safe"]      * 12 +
    ["warning_g"] * 4  +
    ["warning_t"] * 3  +
    ["no_helmet"] * 2  +
    ["danger"]    * 2  +
    ["fall"]      * 1
)

def jitter(v, pct=0.07):
    if isinstance(v, bool): return v
    if isinstance(v, int):  return max(0, round(v + random.uniform(-v * pct, v * pct)))
    return round(max(0.0, v + random.uniform(-v * pct, v * pct)), 2)

def build_payload(worker_id, tpl, wave):
    t = TEMPLATES[tpl]
    return {
        "worker":                worker_id,
        "gas_level":             jitter(t["gas"]  * (0.85 + wave * 0.3)),
        "temperature":           jitter(t["temp"] * (0.95 + wave * 0.1)),
        "humidity":              jitter(t["hum"]),
        "heart_rate":            jitter(t["hr"] + int(wave * 10)),
        "fall_detected":         t["fall"],
        "helmet_worn":           t["helmet"],
        "nearest_gps_sensor_id": random.choice(GPS_SENSOR_IDS),
        "distance_from_sensor":  round(random.uniform(1.0, 50.0), 1),
    }

def label(p):
    if p["fall_detected"]:          return "⚠️  FALL     "
    if not p["helmet_worn"]:        return "🪖 NO HELMET"
    if p["gas_level"] >= 9:         return "🔴 DANGER   "
    if p["gas_level"] >= 4:         return "🟡 WARNING  "
    return                                 "🟢 safe     "

# ─── Simulation loop ──────────────────────────────────────────────────────────
INTERVAL = 2
print()
print(f"Pushing one reading per worker every {INTERVAL}s.  Ctrl-C to stop.")
print(f"Every 25th tick triggers a crisis event on a random worker.")
print()

tick = 0
try:
    while True:
        wave = (math.sin(tick * 0.157) + 1) / 2

        crisis        = (tick > 0 and tick % 25 == 0)
        crisis_worker = random.choice(WORKER_IDS) if crisis else None

        for wid in WORKER_IDS:
            tpl = random.choice(["danger", "fall"]) if wid == crisis_worker \
                  else random.choice(SCHEDULE)
            p = build_payload(wid, tpl, wave)
            rc.lpush(QUEUE, json.dumps(p))

            print(f"  worker={str(wid).ljust(3)}  {label(p)}  "
                  f"gas={p['gas_level']:5.1f} ppm  "
                  f"temp={p['temperature']:4.1f} °C  "
                  f"hr={p['heart_rate']:3d} bpm  "
                  f"sensor={p['nearest_gps_sensor_id']}  "
                  f"dist={p['distance_from_sensor']:4.1f} m")

        if crisis:
            print(f"  *** CRISIS injected for worker {crisis_worker} ***")
        print(f"  {'─'*68}")
        print(f"  tick={tick:04d}  queue depth={rc.llen(QUEUE)}")
        print()
        tick += 1
        time.sleep(INTERVAL)

except KeyboardInterrupt:
    print("\nStopped.")