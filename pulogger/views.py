from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.shortcuts import render, get_object_or_404
from datetime import datetime, timedelta, timezone
from math import floor, ceil

from .models import Datalogger, SensorModel, Sensor, DatumType, SensorModelDatumType, SensorDatum


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


def parseUriDatetime(datetimeStr):
    #input format YYYYMMDDTHHMMSSZ
    uriDatetime = datetime(
        datetimeStr[0:4],
        datetimeStr[4:6],
        datetimeStr[6:8],
        datetimeStr[9:11],
        datetimeStr[12:14],
        datetimeStr[14:16]
    )

    return uriDatetime


def utc_to_local(utc_dt):
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=None)


def get_filter_start_time(request):
    filter_start_time = None
    if 'timeFilter' in request.GET:
        filter_type = request.GET['timeFilter']
        if filter_type == 'lastHour':
            filter_start_time = datetime.now() - timedelta(hours=1)
        elif filter_type == 'lastDay':
            filter_start_time = datetime.now() - timedelta(hours=24)
        elif filter_type == 'lastWeek':
            filter_start_time = datetime.now() - timedelta(days=7)
        elif filter_type == 'lastMonth':
            filter_start_time = datetime.now() - timedelta(days=30)
        elif filter_type == 'lastHalfYear':
            filter_start_time = datetime.now() - timedelta(days=180)
        elif filter_type == 'lastYear':
            filter_start_time = datetime.now() - timedelta(days=356)
        elif filter_type == 'customRange':
            filter_start_time = parseUriDatetime(request.GET['startDatetime'])
        else:
            filter_start_time = datetime.now() - timedelta(hours=6)
    else:
        filter_start_time = datetime.now() - timedelta(hours=1)
    return filter_start_time

def get_filter_end_time(request):
    filter_end_time = None
    if 'timeFilter' in request.GET and request.GET['timeFilter'] == 'customRange':
        filter_end_time = parseUriDatetime(request.GET['endDatetime'])
    else:
        filter_end_time = datetime.now()

    return filter_end_time


UPPER_DATA_COUNT_LIMIT = 5000


def get_filter_usec_threshold(bulk_queryset):
    bulk_data_count = bulk_queryset.count()
    if bulk_data_count > UPPER_DATA_COUNT_LIMIT:
        return UPPER_DATA_COUNT_LIMIT / bulk_data_count * 999999
    else:
        return 999999


def downsample(bulk_queryset):
    usec_threshold = get_filter_usec_threshold(bulk_queryset)
    return bulk_queryset.extra(where=["microsecond(timestamp) <= '{}'".format(usec_threshold)])


def get_chart_trace_name(sensor_name, datum_type):
    return '{} ({})'.format(sensor_name, datum_type)


def get_chart_trace_id(sensor_id, type_id):
    return '{}-{}'.format(sensor_id, type_id)


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

    sensors = Sensor.objects.filter(datalogger=device).order_by('pk').select_related('type')
    sensor_count = len(sensors)  # should be no worse than count() since already-evaluated and cached.  todo: confirm
    sensor_models = sensors.values_list('type', flat=True)  # get all models of sensor used by this controller
    sensor_model_datum_types = list(SensorModelDatumType.objects.filter(sensor__in=sensor_models).order_by('sensor',
                                                                                                     'datum_type'))  # get all datatypes relating to all models of sensor used

    # assign each trace (sensor/datum_type combination) an indice for the tuples (zero is used for time/x-axis)
    bulk_queryset = SensorDatum.objects.filter(sensor__datalogger__device_name=device_name,
                                               timestamp__gte=get_filter_start_time(request),
                                               timestamp__lte=get_filter_end_time(request))
    downsampled_queryset = downsample(
        SensorDatum.objects.filter(sensor__datalogger__device_name=device_name,
                                   timestamp__gte=get_filter_start_time(request),
                                   timestamp__lte=get_filter_end_time(request))
    ).order_by('timestamp', 'sensor_id', 'type_id')

    chart_traces = []
    chart_trace_indices = {}
    next_free_idx = 1
    for sensor in sensors:
        for sensor_model_datum_type in sensor_model_datum_types:
            if sensor_model_datum_type.sensor == sensor.type:
                chart_trace_name = get_chart_trace_name(sensor.sensor_name,
                                                        sensor_model_datum_type.datum_type.description)
                chart_traces.append(
                    {'sensor': sensor.sensor_name, 'datum_type': sensor_model_datum_type.datum_type.description,
                                     'chart_trace_name': chart_trace_name})
                chart_trace_indices.update(
                    {get_chart_trace_id(sensor.id, sensor_model_datum_type.datum_type_id): next_free_idx})
                next_free_idx += 1

    # process data into timestamp-grouped tuples accessible by chart_trace_index ([0] is timestamp)
    raw_data = downsampled_queryset.values()
    data = []

    for datum in raw_data:
        if len(data) == 0 or datum['timestamp'] != data[-1][0]:
            data.append([datum['timestamp']])
            data[-1].extend([None] * len(chart_traces))

        data[-1][chart_trace_indices[get_chart_trace_id(datum['sensor_id'], datum['type_id'])]] = datum['value']

    column_labels = ['Time']
    column_types = ["datetime"]
    for chart_trace in chart_traces:
        column_labels.append(chart_trace['chart_trace_name'])
        column_types.append("number")

    gchart_json = prepare_data_for_gchart(column_labels, column_types, data)

    context = {
        'device': device_name,
        'sensor_count': sensor_count,
        'sensor_indices': chart_trace_indices,
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