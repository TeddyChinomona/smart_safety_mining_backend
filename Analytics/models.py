from django.db import models
from django.conf import settings


class Zone(models.Model):
    RISK_CHOICES = (
        ('safe', 'Safe'),
        ('warning', 'Warning'),
        ('unsafe', 'Unsafe'),
    )
    name = models.CharField(max_length=100)
    coordinates = models.JSONField(help_text="Store geofence polygon coordinates")
    risk_level = models.CharField(max_length=20, choices=RISK_CHOICES, default='safe')

    def __str__(self):
        return self.name

class SensorEvent(models.Model):
    worker = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    gas_level = models.FloatField(null=True, blank=True)
    temperature = models.FloatField(null=True, blank=True)
    humidity = models.FloatField(null=True, blank=True)
    heart_rate = models.IntegerField(null=True, blank=True)
    fall_detected = models.BooleanField(default=False)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    transponder_id = models.CharField(max_length=100, null=True, blank=True, help_text="Nearest Bluetooth receiver ID")
    location_x = models.FloatField(null=True, blank=True, help_text="Triangulated indoor X coordinate")
    location_y = models.FloatField(null=True, blank=True, help_text="Triangulated indoor Y coordinate")
    helmet_worn = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.worker} - {self.timestamp}"

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
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.worker} - {self.status}"

class Alert(models.Model):
    SEVERITY_CHOICES = (
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical')
    )
    STATUS_CHOICES = (
        ('new', 'New'),
        ('acknowledged', 'Acknowledged'),
        ('resolved', 'Resolved')
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
        ('resolved', 'Resolved')
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='reported_incidents', on_delete=models.CASCADE)
    linked_alert = models.ForeignKey(Alert, null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
