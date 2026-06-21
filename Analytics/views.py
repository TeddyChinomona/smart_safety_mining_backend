import csv
from django.http import HttpResponse
from django.db.models import Count
from django.utils import timezone
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import (
    Zone, MiningSession, GPSSensor,
    SensorEvent, WorkerStatus, Alert, Incident,
)
from .serializers import (
    ZoneSerializer, MiningSessionSerializer, GPSSensorSerializer,
    SensorEventSerializer, WorkerStatusSerializer,
    AlertSerializer, IncidentSerializer,
)
from AuthUser.permissions import IsAdminRole, IsSafetyOfficerRole, IsManagerRole


class ZoneViewSet(viewsets.ModelViewSet):
    queryset = Zone.objects.all()
    serializer_class = ZoneSerializer

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            # Combine CLASSES with `|`, then instantiate once — DRF's
            # permission composability lives on the metaclass, not on
            # instances. IsAdminRole() | IsSafetyOfficerRole() raises
            # TypeError because plain instances have no __or__.
            return [(IsAdminRole | IsSafetyOfficerRole)()]
        return [IsAuthenticated()]


class MiningSessionViewSet(viewsets.ModelViewSet):
    """
    Frontend-facing lifecycle management for mining sessions.

    POST /api/mining-sessions/           → start a session (creates Zone if needed)
    POST /api/mining-sessions/{id}/end/  → complete the session; deactivates GPS sensors
    GET  /api/mining-sessions/active/    → list all currently running sessions
    """
    queryset = MiningSession.objects.select_related('zone', 'started_by').all()
    serializer_class = MiningSessionSerializer

    def get_permissions(self):
        if self.action in ('create', 'end_session', 'destroy'):
            return [(IsAdminRole | IsSafetyOfficerRole | IsManagerRole)()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        serializer.save(started_by=self.request.user)

    @action(detail=True, methods=['post'], url_path='end')
    def end_session(self, request, pk=None):
        """Mark a session as completed and deactivate its GPS sensors."""
        session = self.get_object()
        if session.status != 'active':
            return Response(
                {'error': 'Session is not active.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        session.status = 'completed'
        session.ended_at = timezone.now()
        session.save()

        GPSSensor.objects.filter(session=session).update(is_active=False)

        return Response(MiningSessionSerializer(session).data)

    @action(detail=False, methods=['get'], url_path='active')
    def active_sessions(self, request):
        """List all currently active mining sessions."""
        sessions = MiningSession.objects.filter(status='active').select_related('zone')
        return Response(MiningSessionSerializer(sessions, many=True).data)


class GPSSensorViewSet(viewsets.ModelViewSet):
    """
    Manage registered GPS sensors (Device 1).
    Their positions and session assignments are updated by the Celery GPS task.
    """
    queryset = GPSSensor.objects.select_related('session').all()
    serializer_class = GPSSensorSerializer

    def get_permissions(self):
        return [(IsAdminRole | IsSafetyOfficerRole | IsManagerRole)()]


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
        return [(IsAdminRole | IsManagerRole | IsSafetyOfficerRole)()]


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
        return [(IsAdminRole | IsManagerRole | IsSafetyOfficerRole)()]

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Return a JSON safety summary (total alerts, open incidents, breakdown)."""
        severity_counts = Alert.objects.values('severity').annotate(count=Count('severity'))
        return Response({
            'total_alerts':       Alert.objects.count(),
            'open_incidents':     Incident.objects.filter(status='open').count(),
            'active_sessions':    MiningSession.objects.filter(status='active').count(),
            'alerts_by_severity': list(severity_counts),
        })

    @action(detail=False, methods=['get'])
    def export_csv(self, request):
        """Download alert history as a CSV file."""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="safety_report.csv"'

        writer = csv.writer(response)
        writer.writerow(['ID', 'Alert Type', 'Severity', 'Status', 'Timestamp', 'Worker'])

        for alert in Alert.objects.select_related('worker').order_by('-timestamp'):
            writer.writerow([
                alert.id, alert.alert_type, alert.severity,
                alert.status, alert.timestamp, alert.worker.username,
            ])

        return response