import json

import redis
from loguru import logger
from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import (
    SensorEvent, WorkerStatus, Zone, Alert,
    GPSSensor, GPSSensorReading, MiningSession,
)
from .serializers import (
    SensorEventSerializer, WorkerStatusSerializer, ZoneSerializer,
)

redis_client = redis.StrictRedis(host='redis', port=6379, db=0)
User = get_user_model()


# ─── Device 1: GPS Sensor Pipeline ────────────────────────────────────────────

@shared_task
def process_gps_sensor_data():
    """
    Pulls GPS device readings from the 'gps_sensor_data' Redis queue.

    For each reading:
      1.  Updates GPSSensor.last_latitude / last_longitude (current fix)
      2.  Appends a GPSSensorReading log entry
      3.  Recomputes Zone.coordinates (convex hull of all session readings)
      4.  Broadcasts the updated Zone via WebSocket → frontend redraws fence
    """
    for _ in range(50):
        data = redis_client.lpop('gps_sensor_data')
        if not data:
            break

        try:
            payload = json.loads(data)
            sensor_id = payload.get('sensor_id')
            session_id = payload.get('session_id')
            latitude = payload.get('latitude')
            longitude = payload.get('longitude')

            if not sensor_id or latitude is None or longitude is None:
                logger.warning("GPS payload missing required fields; skipping.")
                continue

            # ── Resolve session ────────────────────────────────────────────
            session = None
            if session_id:
                try:
                    session = MiningSession.objects.get(id=session_id, status='active')
                except MiningSession.DoesNotExist:
                    logger.warning(f"MiningSession {session_id} not found or not active.")

            # ── Upsert GPS sensor record ───────────────────────────────────
            gps_sensor, _ = GPSSensor.objects.get_or_create(
                sensor_id=sensor_id,
                defaults={'session': session, 'is_active': True},
            )
            if session and gps_sensor.session_id != (session.id if session else None):
                gps_sensor.session = session

            gps_sensor.last_latitude = latitude
            gps_sensor.last_longitude = longitude
            gps_sensor.last_seen = timezone.now()
            gps_sensor.save()

            # ── Log individual reading ─────────────────────────────────────
            GPSSensorReading.objects.create(
                sensor=gps_sensor,
                latitude=latitude,
                longitude=longitude,
                altitude=payload.get('altitude'),
            )

            # ── Recompute geofence and broadcast ───────────────────────────
            if gps_sensor.session and gps_sensor.session.status == 'active':
                _recompute_zone_geofence(gps_sensor.session)

                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    'zone_updates',
                    {
                        'type': 'zone_update_message',
                        'data': ZoneSerializer(gps_sensor.session.zone).data,
                    },
                )

        except Exception as e:
            logger.error(f"Error processing GPS sensor data: {e}")


def _recompute_zone_geofence(session: MiningSession) -> None:
    """
    Builds or refreshes Zone.coordinates using the convex hull of all
    GPS readings logged under this session.  Requires ≥ 3 distinct points.

    Coordinate order: (longitude, latitude) — consistent with Shapely's
    (x, y) convention and the downstream geofencing check in
    process_iot_sensor_data.
    """
    points = list(
        GPSSensorReading.objects
        .filter(sensor__session=session, sensor__is_active=True)
        .values_list('longitude', 'latitude')   # (x, y) for Shapely
    )

    if len(points) < 3:
        return  # Not enough points to form a polygon yet

    try:
        from shapely.geometry import MultiPoint

        hull = MultiPoint(points).convex_hull
        if hull.geom_type != 'Polygon':
            return  # Still collinear — wait for more readings

        zone = session.zone
        zone.coordinates = list(hull.exterior.coords)   # [[lon, lat], ...]
        zone.save(update_fields=['coordinates'])
        logger.info(
            f"Zone '{zone.name}' geofence updated: "
            f"{len(points)} readings → {len(zone.coordinates)}-vertex hull."
        )
    except ImportError:
        logger.warning("shapely not installed; geofence recomputation skipped.")
    except Exception as e:
        logger.error(f"Geofence recomputation failed: {e}")


# ─── Device 2: BLE Worker Wearable Pipeline ───────────────────────────────────

@shared_task
def process_iot_sensor_data():
    """
    Pulls BLE wearable readings from the 'iot_sensor_data' Redis queue.

    Each payload carries environmental sensor data plus the ID of the nearest
    GPS sensor and a BLE distance estimate — no raw GPS coordinates.

    Geofencing logic:
      Worker approximate position  ≈  nearest GPS sensor's last lat/lon fix.
      The BLE distance modulates alert severity (closer → more critical).
    """
    for _ in range(50):
        data = redis_client.lpop('iot_sensor_data')
        if not data:
            break

        try:
            payload = json.loads(data)
            worker = User.objects.get(id=payload.get('worker'))

            # ── Resolve nearest GPS sensor ─────────────────────────────────
            nearest_gps_sensor = None
            nearest_sensor_id = payload.get('nearest_gps_sensor_id')
            if nearest_sensor_id:
                try:
                    nearest_gps_sensor = GPSSensor.objects.select_related('session').get(
                        sensor_id=nearest_sensor_id,
                        is_active=True,
                    )
                except GPSSensor.DoesNotExist:
                    logger.warning(f"GPSSensor '{nearest_sensor_id}' not found.")

            # Session is inherited from the GPS sensor the wearable sees —
            # workers don't need to carry a session_id themselves.
            session = nearest_gps_sensor.session if nearest_gps_sensor else None

            # ── Persist BLE sensor event ───────────────────────────────────
            sensor_event = SensorEvent.objects.create(
                worker=worker,
                session=session,
                gas_level=payload.get('gas_level'),
                temperature=payload.get('temperature'),
                humidity=payload.get('humidity'),
                heart_rate=payload.get('heart_rate'),
                fall_detected=payload.get('fall_detected', False),
                helmet_worn=payload.get('helmet_worn', True),
                nearest_gps_sensor=nearest_gps_sensor,
                distance_from_sensor=payload.get('distance_from_sensor'),
            )

            # ── WorkerStatus — create early so broadcast never fails ───────
            worker_status, _ = WorkerStatus.objects.get_or_create(worker=worker)
            if session:
                worker_status.current_session = session

            # ── AI risk prediction ─────────────────────────────────────────
            risk_level = 0
            try:
                from .ai_services import predict_risk_level
                risk_level = predict_risk_level(sensor_event)
                status_map   = {0: 'safe', 1: 'warning', 2: 'danger'}
                severity_map = {1: 'medium', 2: 'critical'}
                worker_status.status = status_map.get(risk_level, 'safe')

                if risk_level > 0:
                    Alert.objects.create(
                        worker=worker,
                        sensor_event=sensor_event,
                        alert_type="AI Detected Abnormal Pattern",
                        severity=severity_map.get(risk_level, 'high'),
                        status='new',
                    )
            except ImportError:
                worker_status.status = 'safe'

            # ── BLE Geofencing ─────────────────────────────────────────────
            #
            # Worker's approximate position  = nearest GPS sensor's last fix.
            # Both Zone.coordinates and the GPS sensor's last_longitude /
            # last_latitude are in the same (lon, lat) space — consistent with
            # Shapely's (x, y) convention.
            #
            # distance_from_sensor is the BLE estimate; it modulates severity
            # (the worker is within that radius of the reference point, so a
            #  small distance means they are very close to the sensor — and
            #  therefore very close to whichever zone boundary it anchors).
            if (
                nearest_gps_sensor
                and nearest_gps_sensor.last_latitude is not None
                and nearest_gps_sensor.last_longitude is not None
            ):
                try:
                    from shapely.geometry import Point, Polygon

                    # Approximate worker position from GPS sensor's last fix
                    worker_point = Point(
                        nearest_gps_sensor.last_longitude,
                        nearest_gps_sensor.last_latitude,
                    )
                    distance = sensor_event.distance_from_sensor or 0.0

                    for zone in Zone.objects.exclude(risk_level='safe'):
                        if not zone.coordinates or len(zone.coordinates) < 3:
                            continue

                        poly = Polygon(zone.coordinates)
                        if not poly.contains(worker_point):
                            continue

                        worker_status.current_zone = zone

                        # Severity ladder: unsafe zone + very close → critical
                        if zone.risk_level == 'unsafe' and distance < 5:
                            severity = 'critical'
                        elif zone.risk_level == 'unsafe':
                            severity = 'high'
                        else:
                            severity = 'medium'

                        Alert.objects.create(
                            worker=worker,
                            sensor_event=sensor_event,
                            alert_type=(
                                f"Entered {zone.risk_level.title()} Zone: {zone.name} "
                                f"(~{distance:.1f} m from sensor {nearest_gps_sensor.sensor_id})"
                            ),
                            severity=severity,
                            status='new',
                        )
                        break   # One zone alert per event is enough

                except ImportError:
                    logger.warning("shapely not installed; BLE geofencing skipped.")

            worker_status.save()

            # ── WebSocket broadcast ────────────────────────────────────────
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                'sensor_events',
                {'type': 'sensor_event_message', 'data': SensorEventSerializer(sensor_event).data},
            )
            async_to_sync(channel_layer.group_send)(
                'worker_statuses',
                {'type': 'worker_status_message', 'data': WorkerStatusSerializer(worker_status).data},
            )

        except Exception as e:
            logger.error(f"Error processing BLE sensor data: {e}")