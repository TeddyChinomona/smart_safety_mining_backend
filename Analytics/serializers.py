from rest_framework import serializers
from .models import Zone, SensorEvent, WorkerStatus, Alert, Incident


class ZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Zone
        fields = '__all__'

class SensorEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = SensorEvent
        fields = '__all__'

class WorkerStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkerStatus
        fields = '__all__'

class AlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alert
        fields = '__all__'

class IncidentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Incident
        fields = '__all__'