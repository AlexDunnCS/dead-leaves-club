from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.shortcuts import render, get_object_or_404
from datetime import datetime

from .models import Datalogger, SensorModel, Sensor, DatumType, SensorModelDatumType, SensorDatum


class DataTypeMismatchError(Exception):
    def __init__(self, message):
        self.message = message

def prepare_data_for_gchart(column_labels, column_types, data):
    column_count = len(data[0])
    # check that column count is correct for all arguments
    assert (len(column_labels) == column_count)
    assert (len(column_types) == column_count)

    column_defs = '"cols": [\n'
    for idx in range(0, column_count):
        column_defs += '{{"id":"","label":"{}","pattern":"","type":"{}"}},\n'.format(column_labels[idx], column_types[idx])
    column_defs += ']'  # todo: remove final comma for browser compatibility, remove debug linebreak

    row_defs = '"rows": [\n'
    for datum in data:
        row_defs += '{"c":[\n'
        for idx in range(0, column_count):
            row_defs +='{{"v":"{}","f":null}},\n'.format(datum[idx]) # todo: remove final comma for browser compatibility, remove debug linebreak
        row_defs += ']},\n'
    row_defs += ']'

    json = '{' + column_defs + ',\n' + row_defs + '}'

    return json


def simpleview(request):
    device_name = request.GET['device']
    device = Datalogger.objects.get(device_name=device_name)

    sensors = Sensor.objects.filter(datalogger=device).order_by('pk')
    sensor_count = len(sensors)  # should be no worse than count() since already-evaluated and cached.  todo: confirm

    #assign each sensor an indice for the tuples (zero is used for time/x-axis)
    sensor_indices = {}
    for idx, sensor in enumerate(sensors, start=1):
        sensor_indices.update({sensor.sensor_name:idx})

    # process data into timestamp-grouped tuples accessible by sensor-index ([0] is timestamp)
    raw_data = SensorDatum.objects.filter(sensor__datalogger__device_name=device_name).order_by('timestamp', 'sensor')
    data = []
    data_idx = 0

    while data_idx < len(raw_data):
        row_list = [raw_data[data_idx].timestamp]
        row_list.extend([None]*sensor_count)
        row_idx = 1

        while data_idx < len(raw_data) and raw_data[data_idx].timestamp == row_list[0]:
            row_idx = sensor_indices.get(raw_data[data_idx].sensor.sensor_name)
            row_list[row_idx] = raw_data[data_idx].value
            data_idx += 1
        data.append(tuple(row_list))

    column_labels = ['Time']
    column_types = ["datetime"]
    for sensor in sensors:
        column_labels.append(sensor.sensor_name)
        column_types.append("number")

    gchart_json = prepare_data_for_gchart(column_labels, column_types, data)
    print(gchart_json)



    context = {
        'device': device_name,
        'sensor_count': sensor_count,
        'sensor_indices': sensor_indices,
        'gchart_json': gchart_json,
    }

    return render(request, 'pulogger/simpleTimeSeriesView.html', context)


def submitdatum(request):
    device = request.GET['device']
    sensor_name = request.GET['sensor']
    datum_type = request.GET['type']
    datum_value = request.GET['value']
    submission_ip = "1.1.1.1"  # placeholder



    try:
        # Check that a valid sensor exists for the parameters provided, else throw exception
        sensor = Sensor.objects.get(
                sensor_name=sensor_name,
                datalogger__device_name=device
        )

        if not SensorModelDatumType.objects.filter(sensor__type=sensor.type.type, datum_type__description=datum_type).exists():
            raise DataTypeMismatchError('Sensor type {} cannot measure {}.'.format(sensor.type.type, datum_type))

        new_datum = SensorDatum(
            submission_ip=submission_ip,
            timestamp=datetime.now(),
            value=datum_value,
            sensor_id=sensor.pk,
            type_id=DatumType.objects.get(description=datum_type).pk,
        )

        new_datum.full_clean()
        new_datum.save()

        context = {
            'success': True,
            'response': str(new_datum)
        }
    except ValidationError:
        context = {
            'success': False,
            'response': 'Error: Submitted datum failed validation.'

        }
    except ObjectDoesNotExist:
        context = {
            'success': False,
            'response': 'Error: No such device, or no such sensor named {} attached to device.'.format(sensor_name)

        }
    except DataTypeMismatchError as err:
        context = {
            'success': False,
            'response': err.message
        }

    return render(request, 'pulogger/submitDatumResponse.html', context)


def index(request):
    return render(request, 'pulogger/index.html', None)