#!/usr/bin/env python3
"""
run_simulators.py — Docker Compose simulation orchestrator.

Sequence
────────
1. Poll GET /auth/login/ until the Django web service responds (≤ STARTUP_MAX s).
   This covers the time for migrate + setup_demo + Daphne startup.

2. Launch simulate_gps.py as a background subprocess (non-interactive; reads
   all config from environment variables).

3. Wait GPS_WARMUP seconds.  During this window the Celery GPS task fires
   (every 3 s) and calls GPSSensor.objects.get_or_create() for each sensor ID
   in the payload, registering them in the database.

4. Launch simulate_iot.py in the foreground (non-interactive).  By now GPS
   sensors exist so BLE geofencing can resolve nearest_gps_sensor correctly.

5. Block until either process exits, then terminate the other and exit cleanly.

Environment variables (set in docker-compose.yaml)
───────────────────────────────────────────────────
  API_BASE       URL of the Django web service  (default: http://127.0.0.1:8000)
  STARTUP_MAX    Max seconds to wait for the API (default: 90)
  GPS_WARMUP     Seconds GPS runs before BLE starts (default: 20)
"""

import os
import subprocess
import sys
import time

try:
    import requests
except ImportError:
    print("[orchestrator] 'requests' is not installed — add it to requirements.txt")
    sys.exit(1)

API_BASE    = os.getenv("API_BASE",    "http://127.0.0.1:8000")
STARTUP_MAX = int(os.getenv("STARTUP_MAX", "90"))
GPS_WARMUP  = int(os.getenv("GPS_WARMUP",  "20"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def wait_for_api(max_seconds: int) -> bool:
    """
    Poll the login endpoint until it returns any HTTP response.
    A 405 Method Not Allowed is fine — it means Daphne is up and routing works.
    """
    print(f"[orchestrator] Waiting up to {max_seconds}s for {API_BASE} …")
    deadline = time.time() + max_seconds
    attempt  = 0
    while time.time() < deadline:
        attempt += 1
        try:
            r = requests.get(f"{API_BASE}/auth/login/", timeout=4)
            if r.status_code in (200, 405):
                print(f"[orchestrator] API ready after {attempt} attempt(s).")
                return True
        except Exception as exc:
            print(f"[orchestrator]   attempt {attempt}: {exc}")
        time.sleep(3)
    return False


def launch(script: str) -> subprocess.Popen:
    """Start a simulator script as a non-interactive subprocess."""
    proc = subprocess.Popen(
        [sys.executable, script],
        stdin=subprocess.DEVNULL,   # no interactive input — scripts read env vars
    )
    print(f"[orchestrator] {script} started  (PID {proc.pid})")
    return proc


def terminate(proc: subprocess.Popen, name: str) -> None:
    if proc and proc.poll() is None:
        print(f"[orchestrator] Stopping {name} (PID {proc.pid}) …")
        proc.terminate()
        try:
            proc.wait(timeout=6)
        except subprocess.TimeoutExpired:
            proc.kill()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if not wait_for_api(STARTUP_MAX):
        print(f"[orchestrator] Timed out after {STARTUP_MAX}s — aborting.")
        sys.exit(1)

    gps = iot = None

    try:
        # Phase 1 — GPS sensors (Device 1)
        gps = launch("simulate_gps.py")
        print(f"[orchestrator] Waiting {GPS_WARMUP}s for GPS sensors to register …")
        time.sleep(GPS_WARMUP)

        # Phase 2 — BLE wearables (Device 2)
        iot = launch("simulate_iot.py")
        print("[orchestrator] Both simulators active. Press Ctrl-C to stop.\n")

        # Wait for either process to exit unexpectedly
        while True:
            if gps.poll() is not None:
                print(f"[orchestrator] GPS exited (code {gps.returncode}) — stopping.")
                break
            if iot.poll() is not None:
                print(f"[orchestrator] BLE exited (code {iot.returncode}) — stopping.")
                break
            time.sleep(2)

    except KeyboardInterrupt:
        print("\n[orchestrator] Interrupt received.")

    finally:
        terminate(gps, "simulate_gps.py")
        terminate(iot, "simulate_iot.py")
        print("[orchestrator] Done.")


if __name__ == "__main__":
    main()
