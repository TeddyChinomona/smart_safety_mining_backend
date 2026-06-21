#!/usr/bin/env python3
"""
Smart Safety Mining — GPS sensor (Device 1) simulator.

Runs in two modes:
  Interactive  — run directly from a terminal; prompts for credentials.
  Docker/CI    — all config via environment variables; no prompts shown.

Environment variables
─────────────────────
  ADMIN_USERNAME    API login username       (default: prompt)
  ADMIN_PASSWORD    API login password       (default: prompt)
  API_BASE          Django base URL          (default: http://127.0.0.1:8000)
  REDIS_HOST        Redis hostname           (default: 127.0.0.1)
  REDIS_PORT        Redis port               (default: 6379)
  ZONE_NAME         Zone to create if none   (default: prompt / "Simba Shaft A")
  SESSION_NAME      Session name             (default: prompt / "Morning Shift")
  GPS_SENSOR_IDS    Space-separated IDs      (default: prompt / GPS-001 GPS-002 GPS-003)

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
QUEUE      = "gps_sensor_data"

_non_interactive = bool(os.getenv("ADMIN_USERNAME"))   # True = Docker mode

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

def get_active_sessions(token):
    r = requests.get(f"{API_BASE}/api/mining-sessions/active/",
                     headers=_h(token), timeout=10)
    return r.json() if r.ok else []

def create_zone(token, name):
    r = requests.post(f"{API_BASE}/api/zones/",
                      json={"name": name, "risk_level": "safe", "coordinates": []},
                      headers=_h(token), timeout=10)
    if not r.ok:
        print(f"✗ Zone creation failed ({r.status_code}): {r.text}")
        sys.exit(1)
    z = r.json()
    print(f"  ✓ Zone '{z['name']}' created  (id={z['id']})")
    return z

def create_session(token, zone_id, name):
    r = requests.post(f"{API_BASE}/api/mining-sessions/",
                      json={"zone": zone_id, "name": name},
                      headers=_h(token), timeout=10)
    if not r.ok:
        print(f"✗ Session creation failed ({r.status_code}): {r.text}")
        sys.exit(1)
    s = r.json()
    print(f"  ✓ Session '{s['name']}' created  (id={s['id']})")
    return s

# ─── Banner ────────────────────────────────────────────────────────────────────
print()
print("╔══════════════════════════════════════════════════════════════╗")
print("║   Smart Safety Mining — GPS Sensor Simulator (Device 1)     ║")
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

# ─── Session ──────────────────────────────────────────────────────────────────
sessions = get_active_sessions(token)
if sessions:
    session = sessions[0]
    print(f"✓ Using existing active session: '{session['name']}'  (id={session['id']})")
else:
    print("No active session found — creating one now.")
    zone_name    = _ask("ZONE_NAME",    "Zone name    [Simba Shaft A]: ", "Simba Shaft A")
    session_name = _ask("SESSION_NAME", "Session name [Morning Shift]:  ", "Morning Shift")
    zone    = create_zone(token, zone_name)
    session = create_session(token, zone["id"], session_name)

SESSION_ID = session["id"]

# ─── Sensor IDs ───────────────────────────────────────────────────────────────
# Auto-registered in DB on first reading via GPSSensor.objects.get_or_create().
print()
raw_ids = _ask("GPS_SENSOR_IDS",
               "GPS Sensor IDs [GPS-001 GPS-002 GPS-003]: ",
               "GPS-001 GPS-002 GPS-003")
SENSOR_IDS = raw_ids.split()

print()
print("─" * 64)
print(f"  Session  : '{session['name']}'  (id={SESSION_ID})")
print(f"  Sensors  : {SENSOR_IDS}")
print(f"  Note     : ≥ 3 GPS readings needed before fence polygon appears")
print("─" * 64)

# ─── Mine site parameters (Harare-area approximation) ─────────────────────────
BASE_LAT = -17.829
BASE_LON =  31.052
RADIUS_M =  0.003    # ≈ 300 m in decimal degrees
INTERVAL =  3

print()
print(f"Pushing GPS readings every {INTERVAL}s.  Ctrl-C to stop.")
print(f"{'Sensor':<12}  {'Latitude':>12}  {'Longitude':>12}  {'Altitude':>10}")
print("─" * 52)

tick = 0
try:
    while True:
        for i, sensor_id in enumerate(SENSOR_IDS):
            phase  = i * (2 * math.pi / len(SENSOR_IDS))
            angle  = (tick * 0.04 + phase) % (2 * math.pi)
            radius = RADIUS_M * (0.8 + 0.4 * math.sin(tick * 0.03 + phase))

            lat = round(BASE_LAT + radius * math.sin(angle), 6)
            lon = round(BASE_LON + radius * math.cos(angle), 6)
            alt = round(1200.0 + random.uniform(-3, 3), 1)

            payload = {
                "sensor_id":  sensor_id,
                "session_id": SESSION_ID,
                "latitude":   lat,
                "longitude":  lon,
                "altitude":   alt,
            }
            rc.lpush(QUEUE, json.dumps(payload))
            print(f"{sensor_id:<12}  {lat:>12.6f}  {lon:>12.6f}  {alt:>8.1f} m")

        print(f"  tick={tick:04d}  queue depth={rc.llen(QUEUE)}")
        print()
        tick += 1
        time.sleep(INTERVAL)

except KeyboardInterrupt:
    print("\nStopped.")