#!/usr/bin/env python3
"""
Smart Safety Mining — BLE wearable (Device 2) simulator.

Pushes worker sensor payloads to Redis 'iot_sensor_data'.
Location is expressed as (nearest_gps_sensor_id, distance_from_sensor)
— not raw GPS coordinates, which belong to simulate_gps.py.

Requirements:  pip install redis
Usage:         python simulate_iot.py
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

QUEUE = "iot_sensor_data"
rc    = redis.StrictRedis(host="127.0.0.1", port=6379, db=0, decode_responses=True)

try:
    rc.ping()
    print("✓ Connected to Redis 127.0.0.1:6379 / db0")
except redis.ConnectionError:
    print("✗ Cannot reach Redis on 127.0.0.1:6379 — is it running?")
    sys.exit(1)

# ─── Configuration ─────────────────────────────────────────────────────────────
print("\nEnter worker user IDs from your database, space-separated (e.g.  1 2 3):")
raw = input("Worker IDs > ").strip()
WORKER_IDS = [int(x) for x in raw.split()] if raw else [1, 2, 3, 4, 5]

print("\nEnter GPS sensor IDs that are active (must match simulate_gps.py, e.g.  GPS-001 GPS-002):")
raw = input("GPS Sensor IDs > ").strip()
GPS_SENSOR_IDS = raw.split() if raw else ["GPS-001", "GPS-002", "GPS-003"]

print(f"\nWorkers: {WORKER_IDS}")
print(f"GPS sensors: {GPS_SENSOR_IDS}\n")

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
        "worker":               worker_id,
        "gas_level":            jitter(t["gas"]  * (0.85 + wave * 0.3)),
        "temperature":          jitter(t["temp"] * (0.95 + wave * 0.1)),
        "humidity":             jitter(t["hum"]),
        "heart_rate":           jitter(t["hr"] + int(wave * 10)),
        "fall_detected":        t["fall"],
        "helmet_worn":          t["helmet"],
        # BLE positioning: which GPS sensor is nearest + estimated distance
        "nearest_gps_sensor_id": random.choice(GPS_SENSOR_IDS),
        "distance_from_sensor":  round(random.uniform(1.0, 50.0), 1),
    }

def label(p):
    if p["fall_detected"]:                  return "⚠️  FALL     "
    if not p["helmet_worn"]:               return "🪖 NO HELMET"
    if p["gas_level"] >= 9:                return "🔴 DANGER   "
    if p["gas_level"] >= 4:                return "🟡 WARNING  "
    return                                        "🟢 safe     "

# ─── Simulation loop ──────────────────────────────────────────────────────────
INTERVAL = 2
print(f"Pushing one reading per worker every {INTERVAL}s.  Ctrl-C to stop.\n")

tick = 0
try:
    while True:
        wave = (math.sin(tick * 0.157) + 1) / 2

        crisis = (tick > 0 and tick % 25 == 0)
        crisis_worker = random.choice(WORKER_IDS) if crisis else None

        for wid in WORKER_IDS:
            tpl = random.choice(["danger", "fall"]) if wid == crisis_worker else random.choice(SCHEDULE)
            p = build_payload(wid, tpl, wave)
            rc.lpush(QUEUE, json.dumps(p))

            print(f"  worker={str(wid).ljust(3)}  {label(p)}  "
                  f"gas={p['gas_level']:5.1f} ppm  "
                  f"temp={p['temperature']:4.1f} °C  "
                  f"hr={p['heart_rate']:3d} bpm  "
                  f"sensor={p['nearest_gps_sensor_id']}  "
                  f"dist={p['distance_from_sensor']:4.1f} m")

        print(f"  {'─'*68}")
        print(f"  tick={tick:04d}  queue depth={rc.llen(QUEUE)}\n")
        tick += 1
        time.sleep(INTERVAL)

except KeyboardInterrupt:
    print("\nStopped.")