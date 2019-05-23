from django.db import models


class Datalogger(models.Model):
    device_name = models.CharField(max_length=64)
    description = models.CharField(max_length=64)
    temperature_sensors = models.SmallIntegerField()
    humidity_sensor_count = models.SmallIntegerField()
    up_since = models.DateTimeField('uninterrupted since')
    last_transmission = models.DateTimeField('last transmission received')


class SensorDatum(models.Model):
    device = models.ForeignKey(Datalogger, on_delete=models.DO_NOTHING)
    ip = models.GenericIPAddressField()
    timestamp = models.DateTimeField()

    class Meta:
        abstract = True


class TemperatureDatum(SensorDatum):
    temperature = models.DecimalField(max_digits=4, decimal_places=2)


class HumidityDatum(SensorDatum):
    humidity = models.DecimalField(max_digits=4, decimal_places=2)


# class SensorAlarmEvent(models.Model):
#     device = models.ForeignKey(Datalogger, on_delete=models.DO_NOTHING)
#     timestamp = models.DateTimeField()
#
#     class Meta:
#         abstract = True
