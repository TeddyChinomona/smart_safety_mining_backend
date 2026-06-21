#!/usr/bin/env python3
"""
setup_demo.py — creates (or repairs) the admin user, and flushes any stale
simulation data left over in Redis from a previous container generation.

Deliberately a plain script, NOT a Django management command — that requires
a nested AppName/management/commands/ directory with two __init__.py files,
which is easy to misplace.  This only needs to live in the project root next
to manage.py, exactly like simulate_gps.py and simulate_iot.py already do.

Wired into docker-compose.yaml's `web` service command:
    python manage.py migrate && python setup_demo.py && daphne ...

Idempotent — safe to run on every container start.

Why the Redis flush is here
────────────────────────────
The SQLite DB lives inside the `web` container's writable layer (no volume),
so every time that container is recreated — `docker compose up --build` does
this whenever the image changes — `migrate` runs against a brand-new empty
database and worker/session/zone IDs start counting from 1 again.

Redis, however, can survive that same cycle if Compose decides its image/
config hasn't changed and reuses the existing container.  When that happens,
old GPS/BLE payloads from the *previous* DB generation are still sitting in
the `gps_sensor_data` / `iot_sensor_data` queues, referencing worker and
session IDs that no longer exist in the fresh database — surfacing as:

    CustomUser matching query does not exist
    MiningSession <N> not found or not active

`web`'s boot is the one guaranteed sync point with a known-good DB state, so
clearing both queues here — before the simulator gets a chance to push
anything new — guarantees every payload Celery ever processes references IDs
that actually exist in the database that's currently running.

Environment variables:
    DJANGO_ADMIN_USERNAME   default: admin
    DJANGO_ADMIN_PASSWORD   default: admin123
    DJANGO_ADMIN_EMAIL      default: admin@mine.test
    REDIS_HOST              default: redis
    REDIS_PORT              default: 6379
"""

import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "smart_safety_mining.settings")
django.setup()

from django.contrib.auth import get_user_model

# Queue names used by Analytics/tasks.py — keep in sync if those ever change.
SIMULATION_QUEUES = ("gps_sensor_data", "iot_sensor_data")


def flush_simulation_queues():
    """
    Delete any leftover GPS/BLE payloads from a previous container
    generation.  Safe to run unconditionally — these queues only ever hold
    transient simulator input, never anything that needs to survive a reset.
    """
    try:
        import redis
    except ImportError:
        print("[setup_demo] 'redis' package not installed — skipping queue flush.")
        return

    host = os.getenv("REDIS_HOST", "redis")
    port = int(os.getenv("REDIS_PORT", "6379"))

    try:
        rc = redis.StrictRedis(host='127.0.0.1', port=6379, db=0, socket_connect_timeout=5)
        rc.ping()
        removed = rc.delete(*SIMULATION_QUEUES)
        print(f"[setup_demo] Flushed simulation queues {SIMULATION_QUEUES} "
              f"({removed} key(s) existed and were cleared).")
    except Exception as exc:
        # Non-fatal — worst case is the original stale-ID errors reappear,
        # which is no worse than before this flush existed.
        print(f"[setup_demo] WARNING: could not flush Redis queues ({exc}).")


def main():
    flush_simulation_queues()

    User = get_user_model()

    username = os.getenv("DJANGO_ADMIN_USERNAME", "admin")
    password = os.getenv("DJANGO_ADMIN_PASSWORD", "admin123")
    email    = os.getenv("DJANGO_ADMIN_EMAIL",    "admin@mine.test")

    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            "email":        email,
            "role":         "admin",
            "is_staff":     True,
            "is_superuser": True,
        },
    )

    if created:
        user.set_password(password)
        user.save()
        print(f"[setup_demo] Created admin user '{username}' (role=admin, is_superuser=True).")
        return

    changed = []
    if user.role != "admin":
        user.role = "admin"
        changed.append("role→admin")
    if not user.is_staff:
        user.is_staff = True
        changed.append("is_staff→True")
    if not user.is_superuser:
        user.is_superuser = True
        changed.append("is_superuser→True")

    if changed:
        user.save(update_fields=["role", "is_staff", "is_superuser"])
        print(f"[setup_demo] Updated existing user '{username}': {', '.join(changed)}.")
    else:
        print(f"[setup_demo] Admin user '{username}' already configured correctly.")


if __name__ == "__main__":
    main()