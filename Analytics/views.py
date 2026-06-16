import csv
from django.http import HttpResponse
from django.db.models import Count
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Zone, SensorEvent, WorkerStatus, Alert, Incident
from .serializers import (
    ZoneSerializer, SensorEventSerializer, WorkerStatusSerializer,
    AlertSerializer, IncidentSerializer,
)
from AuthUser.permissions import IsAdminRole, IsSafetyOfficerRole, IsManagerRole


class ZoneViewSet(viewsets.ModelViewSet):
    queryset = Zone.objects.all()
    serializer_class = ZoneSerializer

    def get_permissions(self):
        # Write actions require elevated roles; reads are open to any auth user
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsAdminRole() | IsSafetyOfficerRole()]
        return [IsAuthenticated()]


class SensorEventViewSet(
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    POST / GET are handled via Redis → Celery → WebSocket pipeline.
    HTTP is restricted to admin-level UPDATE and DELETE only.
    """
    queryset = SensorEvent.objects.all()
    serializer_class = SensorEventSerializer

    def get_permissions(self):
        # Python 'or' evaluates to the first truthy object — always wrong here.
        # DRF '|' correctly combines permission classes with OR logic.
        return [IsAdminRole() | IsManagerRole() | IsSafetyOfficerRole()]


class WorkerStatusViewSet(
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """GET worker statuses are delivered via WebSocket; writes go through HTTP."""
    queryset = WorkerStatus.objects.all()
    serializer_class = WorkerStatusSerializer
    permission_classes = [IsAuthenticated]


class AlertViewSet(viewsets.ModelViewSet):
    queryset = Alert.objects.all()
    serializer_class = AlertSerializer
    permission_classes = [IsAuthenticated]


class IncidentViewSet(viewsets.ModelViewSet):
    queryset = Incident.objects.all()
    serializer_class = IncidentSerializer
    permission_classes = [IsAuthenticated]


class AnalyticsViewSet(viewsets.ViewSet):

    def get_permissions(self):
        return [IsAdminRole() | IsManagerRole() | IsSafetyOfficerRole()]

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Return a JSON safety summary (total alerts, open incidents, breakdown)."""
        severity_counts = Alert.objects.values("severity").annotate(count=Count("severity"))
        return Response({
            "total_alerts":        Alert.objects.count(),
            "open_incidents":      Incident.objects.filter(status="open").count(),
            "alerts_by_severity":  list(severity_counts),
        })

    @action(detail=False, methods=["get"])
    def export_csv(self, request):
        """Download alert history as a CSV file."""
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="safety_report.csv"'

        writer = csv.writer(response)
        writer.writerow(["ID", "Alert Type", "Severity", "Status", "Timestamp", "Worker"])

        for alert in Alert.objects.select_related("worker").order_by("-timestamp"):
            writer.writerow([
                alert.id, alert.alert_type, alert.severity,
                alert.status, alert.timestamp, alert.worker.username,
            ])

        return response