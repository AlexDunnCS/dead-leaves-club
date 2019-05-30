from django.contrib import admin

from .models import Datalogger, SensorModel, Sensor, DatumType

admin.site.register(Datalogger)
admin.site.register(SensorModel)
admin.site.register(Sensor)
admin.site.register(DatumType)
