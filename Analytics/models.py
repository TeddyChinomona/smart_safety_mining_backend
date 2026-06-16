from django.db import models
from django.conf import settings


class Zone(models.Model):
    RISK_CHOICES = (
        ('safe', 'Safe'),
        ('warning', 'Warning'),
        ('unsafe', 'Unsafe'),
    )
    name = models.CharField(max_length=100)
    # [[lon, lat], ...] — recomputed by Celery from active GPS sensor readings
    coordinates = models.JSONField(
        default=list,
        help_text="Geofence polygon [[lon, lat], ...]; auto-updated from GPS sensor readings",
    )
    risk_level = models.CharField(max_length=20, choices=RISK_CHOICES, default='safe')

    def __str__(self):
        return self.name


class MiningSession(models.Model):
    """
    A bounded work session started/stopped from the frontend.
    GPS sensors register under a session; the session drives Zone.coordinates updates.
    """
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
    )
    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name='sessions')
    name = models.CharField(max_length=200)
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='mining_sessions',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} — {self.get_status_display()}"


class GPSSensor(models.Model):
    """
    Device 1: a physical GPS unit deployed in the mine.

    Multiple sensors per session collectively define the geofence hull.
    last_latitude / last_longitude are kept current by the Celery GPS task
    so that BLE geofencing can reference the latest fix without an extra join.
    """
    sensor_id = models.CharField(max_length=100, unique=True, help_text="Hardware device ID")
    session = models.ForeignKey(
        MiningSession,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='gps_sensors',
    )
    label = models.CharField(max_length=100, blank=True, help_text="e.g. 'North Tunnel Entry'")
    is_active = models.BooleanField(default=True)
    last_latitude = models.FloatField(null=True, blank=True)
    last_longitude = models.FloatField(null=True, blank=True)
    last_seen = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"GPS:{self.sensor_id} ({self.label or '—'})"


class GPSSensorReading(models.Model):
    """
    One GPS fix from a Device 1 unit.
    Readings accumulate and are used to recompute Zone.coordinates
    (convex hull) for as long as the session is active.
    """
    sensor = models.ForeignKey(GPSSensor, on_delete=models.CASCADE, related_name='readings')
    latitude = models.FloatField()
    longitude = models.FloatField()
    altitude = models.FloatField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    sequence = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.sensor.sensor_id} @ ({self.latitude:.5f}, {self.longitude:.5f})"


class SensorEvent(models.Model):
    """
    Device 2: BLE wearable event emitted by a worker.

    Location is expressed as distance from the nearest GPS sensor (Device 1)
    rather than as absolute GPS coordinates — those belong to GPSSensorReading.
    """
    worker = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    session = models.ForeignKey(
        MiningSession,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='sensor_events',
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    # ── Environmental / biometric sensors (unchanged) ──────────────────────
    gas_level = models.FloatField(null=True, blank=True)
    temperature = models.FloatField(null=True, blank=True)
    humidity = models.FloatField(null=True, blank=True)
    heart_rate = models.IntegerField(null=True, blank=True)
    fall_detected = models.BooleanField(default=False)
    helmet_worn = models.BooleanField(default=True)

    # ── BLE positioning (Device 2 ← Device 1) ─────────────────────────────
    # The wearable scans for the nearest GPS sensor beacon and reports
    # its hardware ID plus the BLE-estimated distance to it.
    nearest_gps_sensor = models.ForeignKey(
        GPSSensor,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='nearby_events',
        help_text="Nearest GPS sensor (Device 1) detected by the BLE wearable",
    )
    distance_from_sensor = models.FloatField(
        null=True, blank=True,
        help_text="BLE-estimated distance to the nearest GPS sensor in metres",
    )

    def __str__(self):
        return f"{self.worker} — {self.timestamp}"


class WorkerStatus(models.Model):
    STATUS_CHOICES = (
        ('safe', 'Safe'),
        ('warning', 'Warning'),
        ('danger', 'Danger'),
        ('offline', 'Offline'),
    )
    worker = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='offline')
    current_zone = models.ForeignKey(Zone, null=True, blank=True, on_delete=models.SET_NULL)
    current_session = models.ForeignKey(
        MiningSession, null=True, blank=True, on_delete=models.SET_NULL
    )
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.worker} — {self.status}"


class Alert(models.Model):
    SEVERITY_CHOICES = (
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    )
    STATUS_CHOICES = (
        ('new', 'New'),
        ('acknowledged', 'Acknowledged'),
        ('resolved', 'Resolved'),
    )
    worker = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    sensor_event = models.ForeignKey(SensorEvent, null=True, blank=True, on_delete=models.SET_NULL)
    alert_type = models.CharField(max_length=100)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Alert: {self.alert_type} ({self.severity})"


class Incident(models.Model):
    STATUS_CHOICES = (
        ('open', 'Open'),
        ('under_review', 'Under Review'),
        ('resolved', 'Resolved'),
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='reported_incidents', on_delete=models.CASCADE
    )
    linked_alert = models.ForeignKey(Alert, null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title