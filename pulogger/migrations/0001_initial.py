# Generated by Django 2.2.1 on 2019-05-23 01:43

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Datalogger',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('device_name', models.CharField(max_length=64)),
                ('description', models.CharField(max_length=64)),
                ('temperature_sensors', models.SmallIntegerField()),
                ('humidity_sensor_count', models.SmallIntegerField()),
                ('up_since', models.DateTimeField(verbose_name='uninterrupted since')),
                ('last_transmission', models.DateTimeField(verbose_name='last transmission received')),
            ],
        ),
        migrations.CreateModel(
            name='TemperatureDatum',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ip', models.GenericIPAddressField()),
                ('timestamp', models.DateTimeField()),
                ('temperature', models.DecimalField(decimal_places=2, max_digits=4)),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, to='pulogger.Datalogger')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='HumidityDatum',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ip', models.GenericIPAddressField()),
                ('timestamp', models.DateTimeField()),
                ('humidity', models.DecimalField(decimal_places=2, max_digits=4)),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, to='pulogger.Datalogger')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
