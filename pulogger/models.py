from django.db import models

PASSCODE_LENGTH = 6

def generate_passcode():
    # Generates a passcode that provides some minimal protection from people posting garbage data
    # It's plaintext, it's passed in the URI, but it's not intended to provide any real security
    import random, string

    passcode = ''.join(random.choice(string.ascii_uppercase + string.digits) for x in range(PASSCODE_LENGTH))

    return passcode

class Datalogger(models.Model):
    device_name = models.CharField(db_index=True, max_length=64)
    description = models.CharField(db_index=True, max_length=64, blank=True)
    passcode = models.CharField(max_length=PASSCODE_LENGTH)
    sensor_count = models.SmallIntegerField(default=1)
    up_since = models.DateTimeField('uninterrupted since', null=True, blank=True)
    last_transmission = models.DateTimeField('last transmission received', null=True, blank=True)

    def __str__(self):
        return '{} ({}) - {} sensors, up since {}, last xmit {}'.format(self.device_name, self.description,
                                                                        self.sensor_count, self.up_since,
                                                                        self.last_transmission)


class SensorModel(models.Model):
    type = models.CharField(db_index=True, max_length=16)
    description = models.CharField(db_index=True, max_length=64, blank=True)

    def __str__(self):
        return '{} ({})'.format(self.type, self.description,)


class Sensor(models.Model):
    datalogger = models.ForeignKey(Datalogger, on_delete=models.CASCADE)
    type = models.ForeignKey(SensorModel, on_delete=models.PROTECT)
    sensor_name = models.CharField(db_index=True, max_length=16)
    description = models.CharField(db_index=True, max_length=64, blank=True)

    def __str__(self):
        return '{} ({}) - {} attached to {}'.format(self.sensor_name, self.description, self.type, self.datalogger)


class DatumType(models.Model):
    description = models.CharField(db_index=True, max_length=16)

    def __str__(self):
        return '{}'.format(self.description)


class SensorModelDatumType(models.Model):
    sensor = models.ForeignKey(SensorModel, on_delete=models.CASCADE)
    datum_type = models.ForeignKey(DatumType, on_delete=models.CASCADE)

    def __str__(self):
        return '{} records {}'.format(self.sensor, self.datum_type)


class SensorDatum(models.Model):
    sensor = models.ForeignKey(Sensor, on_delete=models.CASCADE)
    sensor_name = models.CharField(db_index=True, max_length=16, default='placeholder')
    submission_ip = models.GenericIPAddressField()
    timestamp = models.DateTimeField()
    type = models.ForeignKey(DatumType, on_delete=models.PROTECT)
    value = models.DecimalField(max_digits=4, decimal_places=2)

    def __str__(self):
        return '{}: {} ({}, {}, submitted at {} from {} )'.format(self.type.description, self.value,
                                                                  self.sensor.datalogger.device_name,
                                                                  self.sensor.sensor_name, self.timestamp,
                                                                  self.submission_ip)

    def save(self, *args, **kwargs):
        self.sensor_name = self.sensor.sensor_name  # for fast retrieval in chart views
        super().save(*args, **kwargs)
