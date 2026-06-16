from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/sensor-events/', consumers.SensorEventConsumer.as_asgi()),
    path('ws/worker-statuses/', consumers.WorkerStatusConsumer.as_asgi()),
]