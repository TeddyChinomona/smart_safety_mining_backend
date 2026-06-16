from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ZoneViewSet,
    MiningSessionViewSet,
    GPSSensorViewSet,
    SensorEventViewSet,
    WorkerStatusViewSet,
    AlertViewSet,
    IncidentViewSet,
    AnalyticsViewSet,
)

router = DefaultRouter()
router.register(r'zones',            ZoneViewSet)
router.register(r'mining-sessions',  MiningSessionViewSet)
router.register(r'gps-sensors',      GPSSensorViewSet)
router.register(r'sensor-events',    SensorEventViewSet)
router.register(r'worker-statuses',  WorkerStatusViewSet)
router.register(r'alerts',           AlertViewSet)
router.register(r'incidents',        IncidentViewSet)
router.register(r'analytics',        AnalyticsViewSet, basename='analytics')

urlpatterns = [
    path('', include(router.urls)),
]