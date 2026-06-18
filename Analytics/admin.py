from django.contrib import admin
from .models import *

admin.site.register(Zone)
admin.site.register(MiningSession)
admin.site.register(GPSSensor)
admin.site.register(GPSSensorReading)
admin.site.register(SensorEvent)
admin.site.register(WorkerStatus)
admin.site.register(Alert)
admin.site.register(Incident)