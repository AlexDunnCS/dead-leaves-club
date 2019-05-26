from django.contrib import admin

from .models import Datalogger, SensorModel, Sensor

admin.site.register(Datalogger)
admin.site.register(SensorModel)
admin.site.register(Sensor)