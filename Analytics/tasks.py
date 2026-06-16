import json
import redis
from loguru import logger
from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from .models import SensorEvent, WorkerStatus, Zone, Alert
from .serializers import SensorEventSerializer, WorkerStatusSerializer

redis_client = redis.StrictRedis(host='redis', port=6379, db=0)
User = get_user_model()

@shared_task
def process_iot_sensor_data():
    """
    Pulls IoT data from Redis cache ('iot_sensor_data' list), processes it,
    runs AI/Geofencing, and broadcasts via WebSockets.
    """
    logger.info(f"Processing IoT Sensor Data: {redis_client.ping()}")

    # Process up to 50 events from the queue per run
    for _ in range(50):
        data = redis_client.lpop('iot_sensor_data')
        if not data:
            break
            
        try:
            payload = json.loads(data)
            worker_id = payload.get('worker')
            worker = User.objects.get(id=worker_id)
            
            sensor_event = SensorEvent.objects.create(
                worker=worker,
                gas_level=payload.get('gas_level'),
                temperature=payload.get('temperature'),
                humidity=payload.get('humidity'),
                heart_rate=payload.get('heart_rate'),
                fall_detected=payload.get('fall_detected', False),
                latitude=payload.get('latitude'),
                longitude=payload.get('longitude'),
                transponder_id=payload.get('transponder_id'),
                location_x=payload.get('location_x'),
                location_y=payload.get('location_y'),
                helmet_worn=payload.get('helmet_worn', True)
            )
            
            # --- AI and Geofencing Logic ---
            try:
                from .ai_services import predict_risk_level
                risk_level = predict_risk_level(sensor_event)
                
                status_map = {0: 'safe', 1: 'warning', 2: 'danger'}
                severity_map = {1: 'medium', 2: 'critical'}
                new_status = status_map.get(risk_level, 'safe')
                
                worker_status, _ = WorkerStatus.objects.get_or_create(worker=sensor_event.worker)
                worker_status.status = new_status
                
                if sensor_event.location_x is not None and sensor_event.location_y is not None:
                    try:
                        from shapely.geometry import Point, Polygon
                        point = Point(sensor_event.location_x, sensor_event.location_y)
                        
                        for zone in Zone.objects.exclude(risk_level='safe'):
                            if zone.coordinates and len(zone.coordinates) >= 3:
                                poly = Polygon(zone.coordinates)
                                if poly.contains(point):
                                    worker_status.current_zone = zone
                                    Alert.objects.create(
                                        worker=sensor_event.worker,
                                        sensor_event=sensor_event,
                                        alert_type=f"Entered {zone.risk_level.title()} Zone: {zone.name} (via Transponder {sensor_event.transponder_id or 'Unknown'})",
                                        severity="high" if zone.risk_level == 'unsafe' else "medium",
                                        status='new'
                                    )
                                    break
                    except ImportError:
                        pass
                        
                worker_status.save()
                
                if risk_level > 0:
                    Alert.objects.create(
                        worker=sensor_event.worker,
                        sensor_event=sensor_event,
                        alert_type="AI Detected Abnormal Pattern",
                        severity=severity_map.get(risk_level, 'high'),
                        status='new'
                    )
            except ImportError:
                pass

            # --- WebSocket Broadcasting ---
            channel_layer = get_channel_layer()
            
            async_to_sync(channel_layer.group_send)('sensor_events', {'type': 'sensor_event_message', 'data': SensorEventSerializer(sensor_event).data})
            async_to_sync(channel_layer.group_send)('worker_statuses', {'type': 'worker_status_message', 'data': WorkerStatusSerializer(worker_status).data})

        except Exception as e:
            print(f"Error processing cached IoT data: {e}")