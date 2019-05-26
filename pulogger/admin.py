from django.contrib import admin

from .models import Datalogger, SensorModel, Sensor

admin.register(Datalogger)
admin.register(SensorModel)
admin.register(Sensor)