from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.shortcuts import render, get_object_or_404
from datetime import datetime
from math import floor

from .models import Datalogger, SensorModel, Sensor, DatumType, SensorDatum


class DataTypeMismatchError(Exception):
    def __init__(self, message):
        self.message = message


def get_gchart_datetime_literal(pyDatetime):
    literal = 'Date({}, {}, {}, {}, {}, {}, {})'.format(
        pyDatetime.year,
        (pyDatetime.month - 1),  # js dates are zero-indexed
        pyDatetime.day,
        pyDatetime.hour,
        pyDatetime.minute,
        pyDatetime.second,
        floor(pyDatetime.microsecond / 1000)  # constructor requests milliseconds
    )

    return literal


def get_chart_trace_name(sensor):
    return '{} ({})'.format(sensor.name, sensor.datum_type.description)


def prepare_data_for_gchart(column_labels, column_types, data):
    column_count = len(data[0])
    # check that column count is correct for all arguments
    assert (len(column_labels) == column_count)
    assert (len(column_types) == column_count)

    column_defs = '"cols": [\n'
    for idx in range(0, column_count):
        column_defs += '{{id: "", label: "{}", pattern: "", type: "{}"}}{}\n'.format(column_labels[idx], column_types[idx], ',' if idx < column_count-1 else '')
    column_defs += ']'  # todo: remove debug linebreak

    row_defs = 'rows: [\n'
    for data_idx, datum in enumerate(data):
        row_defs += '{c: ['
        for idx in range(0, column_count):
            datum_value = get_gchart_datetime_literal(datum[idx]) if column_types[idx] == 'datetime' else '{}'.format(datum[idx])
            row_defs +='{{v: "{}", f: null}}{}'.format(datum_value, ', ' if idx < column_count-1 else '') # todo: remove debug linebreak
        row_defs += ']}}{}\n'.format(',' if data_idx < len(data)-1 else '')
    row_defs += ']'

    json = '{' + column_defs + ',\n\n' + row_defs + '}'

    return json


def simpleview(request):
    device_name = request.GET['device']
    device = Datalogger.objects.get(device_name=device_name)

    sensors = Sensor.objects.filter(datalogger=device).order_by('pk').select_related('datum_type')
    sensor_count = len(sensors)  # should be no worse than count() since already-evaluated and cached.  todo: confirm
    # assign each trace (sensor/datum_type combination) an indice for the tuples (zero is used for time/x-axis)
    sensor_indices = {}
    for idx, sensor in enumerate(sensors, start=1):
        sensor_indices.update({sensor: idx})

    # process data into timestamp-grouped tuples accessible by chart_trace_index ([0] is timestamp)
    raw_data = SensorDatum.objects.filter(sensor__datalogger__device_name=device_name).order_by('timestamp', 'sensor')
    row_count = len(raw_data)
    data = []
    data_idx = 0

    while data_idx < row_count:
        data.append([raw_data[data_idx].timestamp])  # create new row, containing timestamp
        data[-1].extend([None] * sensor_count)  # append None placeholders to new row
        row_idx = 1

        while data_idx < row_count and raw_data[data_idx].timestamp == data[-1][0]:
            datum = raw_data[data_idx]
            row_idx = sensor_indices.get(datum.sensor)
            data[-1][row_idx] = datum.value
            data_idx += 1

    column_labels = ['Time']
    column_types = ["datetime"]
    for sensor in sensors:
        column_labels.append(get_chart_trace_name(sensor))
        column_types.append("number")

    gchart_json = prepare_data_for_gchart(column_labels, column_types, data)

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
            name=sensor_name,
            datalogger__device_name=device,
            datum_type__description=datum_type
        )

        new_datum = SensorDatum(
            sensor=sensor,
            submission_ip=submission_ip,
            timestamp=datetime.now(),
            type=sensor.datum_type,
            value=datum_value
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
            'response': 'Error: No such device, '
                        'no such sensor named {} attached to device, '
                        'or sensor cannot measure {}.'.format(sensor_name, datum_type)
        }
    except DataTypeMismatchError as err:
        context = {
            'success': False,
            'response': err.message
        }

    return render(request, 'pulogger/submitDatumResponse.html', context)


def index(request):
    return render(request, 'pulogger/index.html', None)