#!/usr/bin/env python3
"""
Smart Safety Mining — IoT data simulator.

Pushes sensor payloads directly to Redis db0 → Celery task picks them up
→ AI prediction + geofencing → WorkerStatus saved → WebSocket broadcast
→ frontend dashboard updates in real time.

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

# ─── Redis connection ──────────────────────────────────────────────────────────
QUEUE = "iot_sensor_data"
rc    = redis.StrictRedis(host="127.0.0.1", port=6379, db=0, decode_responses=True)

try:
    rc.ping()
    print("✓ Connected to Redis 127.0.0.1:6379 / db0")
except redis.ConnectionError:
    print("✗ Cannot reach Redis on 127.0.0.1:6379 — is it running?")
    sys.exit(1)

# ─── Worker IDs ────────────────────────────────────────────────────────────────
print("\nEnter worker user IDs from your database, space-separated (e.g.  1 2 3):")
raw = input("Worker IDs > ").strip()
WORKER_IDS = [int(x) for x in raw.split()] if raw else [1, 2, 3, 4, 5]
print(f"Simulating workers: {WORKER_IDS}\n")

# ─── Scenario templates ────────────────────────────────────────────────────────
# Tuned to the DecisionTree training data in ai_services.py:
#   gas < 1 & temp < 28 & hr < 85   → Safe    (0)
#   gas 5+ OR temp 30+ OR hr 100+   → Warning (1)
#   gas 10+ AND temp 45+ AND hr 130+ → Danger  (2)
#   fall_detected=True  AND  hr 140+ → Danger  (2)
TEMPLATES = {
    "safe":      dict(gas=0.4,  temp=24.0, hum=48, hr=74,  fall=False, helmet=True),
    "warning_g": dict(gas=5.5,  temp=31.0, hum=57, hr=102, fall=False, helmet=True),
    "warning_t": dict(gas=2.0,  temp=38.0, hum=61, hr=111, fall=False, helmet=True),
    "danger":    dict(gas=11.0, temp=46.0, hum=66, hr=133, fall=False, helmet=False),
    "fall":      dict(gas=0.3,  temp=25.0, hum=50, hr=144, fall=True,  helmet=True),
    "no_helmet": dict(gas=1.0,  temp=27.0, hum=52, hr=79,  fall=False, helmet=False),
}

# Weighted schedule: mostly safe, occasional warning, rare danger
SCHEDULE = (
    ["safe"]      * 12 +
    ["warning_g"] * 4  +
    ["warning_t"] * 3  +
    ["no_helmet"] * 2  +
    ["danger"]    * 2  +
    ["fall"]      * 1
)

def jitter(v, pct=0.07):
    """Add ±7 % random noise so readings look organic."""
    if isinstance(v, bool): return v
    if isinstance(v, int):  return max(0, round(v + random.uniform(-v * pct, v * pct)))
    return round(max(0.0, v + random.uniform(-v * pct, v * pct)), 2)

def build_payload(worker_id, tpl, wave):
    """
    wave is a 0-1 float that makes gas + temp slowly oscillate, so the
    frontend charts show smooth rising/falling curves rather than pure noise.
    """
    t = TEMPLATES[tpl]
    return {
        "worker":         worker_id,
        "gas_level":      jitter(t["gas"]  * (0.85 + wave * 0.3)),
        "temperature":    jitter(t["temp"] * (0.95 + wave * 0.1)),
        "humidity":       jitter(t["hum"]),
        "heart_rate":     jitter(t["hr"]   + int(wave * 10)),
        "fall_detected":  t["fall"],
        "helmet_worn":    t["helmet"],
        "latitude":       round(-17.829 + random.uniform(-0.006, 0.006), 6),
        "longitude":      round( 31.052 + random.uniform(-0.006, 0.006), 6),
        "location_x":     round(random.uniform(10.0, 90.0), 2),
        "location_y":     round(random.uniform(10.0, 90.0), 2),
        "transponder_id": f"BLE-{random.randint(100, 999)}",
    }

def label(p):
    if p["fall_detected"]:    return "⚠️  FALL     "
    if not p["helmet_worn"]:  return "🪖 NO HELMET"
    if p["gas_level"] >= 9:   return "🔴 DANGER   "
    if p["gas_level"] >= 4:   return "🟡 WARNING  "
    return                           "🟢 safe     "

# ─── Simulation loop ──────────────────────────────────────────────────────────
INTERVAL = 2   # seconds between full rounds (one reading per worker per round)
print(f"Pushing one reading per worker every {INTERVAL}s.  Ctrl-C to stop.\n")

tick = 0
try:
    while True:
        # Slow sine wave (period ≈ 40 ticks / 80 s) gives smooth oscillation
        wave = (math.sin(tick * 0.157) + 1) / 2   # 0 → 1

        # Every 25 ticks trigger a "crisis" event for a random worker
        crisis = (tick > 0 and tick % 25 == 0)
        crisis_worker = random.choice(WORKER_IDS) if crisis else None

        for wid in WORKER_IDS:
            if wid == crisis_worker:
                tpl = random.choice(["danger", "fall"])
            else:
                tpl = random.choice(SCHEDULE)

            p = build_payload(wid, tpl, wave)
            rc.lpush(QUEUE, json.dumps(p))

            print(f"  worker={str(wid).ljust(3)}  {label(p)}  "
                  f"gas={p['gas_level']:5.1f} ppm  "
                  f"temp={p['temperature']:4.1f} °C  "
                  f"hr={p['heart_rate']:3d} bpm")

        depth = rc.llen(QUEUE)
        print(f"  {'─'*58}")
        print(f"  tick={tick:04d}  queue depth={depth}  "
              f"(Celery drains this every few seconds)\n")

        tick += 1
        time.sleep(INTERVAL)

except KeyboardInterrupt:
    print("\nStopped.")
