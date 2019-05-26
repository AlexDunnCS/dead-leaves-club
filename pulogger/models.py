from django.db import models


class Datalogger(models.Model):
    device_name = models.CharField(max_length=64)
    description = models.CharField(max_length=64)
    temperature_sensor_count = models.SmallIntegerField()
    humidity_sensor_count = models.SmallIntegerField()
    up_since = models.DateTimeField('uninterrupted since')
    last_transmission = models.DateTimeField('last transmission received')

    def __str__(self):
        return '{} ({}) - {}temp, {}hum, up since {}, last xmit {}'.format(self.device_name, self.description,
                                                                          self.temperature_sensor_count,
                                                                          self.humidity_sensor_count,
                                                                          self.up_since, self.last_transmission)


class SensorModel(models.Model):
    type = models.CharField(max_length=16)
    description = models.CharField(max_length=64)
    has_temperature = models.BooleanField()
    has_humidity = models.BooleanField()

    def __str__(self):
        sensors = []

        if self.has_temperature:
            sensors.append("temperature")

        if self.has_humidity:
            sensors.append("humidity")

        return '{} ({}) - records {}'.format(self.type, self.description, (), ', '.join(sensors))


class Sensor(models.Model):
    datalogger = models.ForeignKey(Datalogger, on_delete=models.CASCADE)
    type = models.ForeignKey(SensorModel, on_delete=models.PROTECT)
    description = models.CharField(max_length=64)

    def __str__(self):
        return '{} ({}) - attached to {}'.format(self.type, self.description, self.datalogger)


class AbstractSensorDatum(models.Model):
    sensor = models.ForeignKey(Sensor, on_delete=models.CASCADE)
    submission_ip = models.GenericIPAddressField()
    timestamp = models.DateTimeField()

    def get_abstract_string(self):
        return '({}, {}, submitted at {} from {} )'.format(self.sensor.datalogger.device_name, self.sensor.description, self.timestamp, self.submission_ip)

    class Meta:
        abstract = True


class TemperatureDatum(AbstractSensorDatum):
    temperature = models.DecimalField(max_digits=4, decimal_places=2)

    def __str__(self):
        return '{} {}'.format(self.temperature, self.get_abstract_string())


class HumidityDatum(AbstractSensorDatum):
    humidity = models.DecimalField(max_digits=4, decimal_places=2)

    def __str__(self):
        return '{} {}'.format(self.humidity, self.get_abstract_string())