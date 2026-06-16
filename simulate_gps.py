#!/usr/bin/env python3
"""
Smart Safety Mining — GPS sensor (Device 1) simulator.

Pushes GPS readings to Redis 'gps_sensor_data'.
Each reading is picked up by process_gps_sensor_data (Celery), which:
  1. Updates GPSSensor.last_latitude / last_longitude
  2. Logs a GPSSensorReading
  3. Recomputes Zone.coordinates (convex hull)
  4. Broadcasts the updated zone polygon via WebSocket

Start a MiningSession first via POST /api/mining-sessions/, then use
the returned ID below.

Requirements:  pip install redis
Usage:         python simulate_gps.py
"""

import json
import math
import random
import sys
import time

try:
    import redis
except ImportError:
    print("Install the redis client first:  pip install redis")
    sys.exit(1)

QUEUE = "gps_sensor_data"
rc    = redis.StrictRedis(host="127.0.0.1", port=6379, db=0, decode_responses=True)

try:
    rc.ping()
    print("✓ Connected to Redis 127.0.0.1:6379 / db0")
except redis.ConnectionError:
    print("✗ Cannot reach Redis on 127.0.0.1:6379 — is it running?")
    sys.exit(1)

# ─── Configuration ─────────────────────────────────────────────────────────────
print("\nEnter the active MiningSession ID (from POST /api/mining-sessions/):")
raw = input("Session ID > ").strip()
SESSION_ID = int(raw) if raw else 1

print("\nEnter GPS Sensor IDs, space-separated (e.g.  GPS-001 GPS-002 GPS-003):")
raw = input("Sensor IDs > ").strip()
SENSOR_IDS = raw.split() if raw else ["GPS-001", "GPS-002", "GPS-003"]

print(f"\nSession: {SESSION_ID}  |  Sensors: {SENSOR_IDS}\n")

# ─── Mine site parameters (Harare-area approximation) ─────────────────────────
# Each GPS sensor traces its own arc around the mine centre, collectively
# forming an expanding/contracting polygon that the convex-hull algorithm
# turns into the live geofence boundary.
BASE_LAT  = -17.829
BASE_LON  =  31.052
RADIUS_M  =  0.003    # ~300 m arc radius in decimal degrees

INTERVAL  =  3        # seconds between full rounds

print(f"Pushing GPS readings every {INTERVAL}s.  Ctrl-C to stop.\n")
print(f"{'Sensor':<12}  {'Latitude':>12}  {'Longitude':>12}  {'Altitude':>10}")
print("─" * 52)

tick = 0
try:
    while True:
        for i, sensor_id in enumerate(SENSOR_IDS):
            # Each sensor occupies a different arc segment so they spread apart
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

        print(f"  tick={tick:04d}  queue depth={rc.llen(QUEUE)}\n")
        tick += 1
        time.sleep(INTERVAL)

except KeyboardInterrupt:
    print("\nStopped.")
