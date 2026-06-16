from rest_framework import serializers
from .models import (
    Zone, MiningSession, GPSSensor, GPSSensorReading,
    SensorEvent, WorkerStatus, Alert, Incident,
)


class ZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Zone
        fields = '__all__'


class MiningSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MiningSession
        fields = '__all__'
        read_only_fields = ('started_by', 'started_at', 'ended_at')


class GPSSensorSerializer(serializers.ModelSerializer):
    class Meta:
        model = GPSSensor
        fields = '__all__'


class GPSSensorReadingSerializer(serializers.ModelSerializer):
    class Meta:
        model = GPSSensorReading
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