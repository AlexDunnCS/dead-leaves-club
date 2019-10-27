from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse

from datetime import datetime, timedelta, timezone
from math import floor, ceil
from decimal import Decimal
from json import dumps as json_dumps

from pulogger.forms import DatetimeRangePicker
from .models import Datalogger, SensorModel, Sensor, DatumType, SensorModelDatumType, SensorDatum


class DataTypeMismatchError(Exception):
    def __init__(self, message):
        self.message = message


def parse_uri_datetime(ms_since_epoch):
    ts_epoch = int(ms_since_epoch) / 1000
    return datetime.fromtimestamp(ts_epoch, tz=timezone.utc)


def datetime_to_js_epoch(dt):
    return floor(dt.timestamp() * 1000)


def datetime_to_sql_format(datetime_obj):
    sql_datetime_str = '{}-{}-{} {}:{}:{}'.format(
        datetime_obj.year,
        datetime_obj.month,  # js dates are zero-indexed
        datetime_obj.day,
        datetime_obj.hour,
        datetime_obj.minute,
        datetime_obj.second,
    )

    return sql_datetime_str


def get_filter_start_time(request):  # todo: remove these filters - they aren't very useful
    if 'timeFilter' in request.GET:
        filter_type = request.GET['timeFilter']
        if filter_type == 'lastHour':
            filter_start_time = datetime.now(tz=timezone.utc) - timedelta(hours=1)
        elif filter_type == 'lastDay':
            filter_start_time = datetime.now(tz=timezone.utc) - timedelta(hours=24)
        elif filter_type == 'lastWeek':
            filter_start_time = datetime.now(tz=timezone.utc) - timedelta(days=7)
        elif filter_type == 'lastMonth':
            filter_start_time = datetime.now(tz=timezone.utc) - timedelta(days=30)
        elif filter_type == 'customRange':
            filter_start_time = parse_uri_datetime(request.GET['from'])
        else:
            filter_start_time = datetime.now(tz=timezone.utc) - timedelta(days=1)
    else:
        filter_start_time = datetime.now(tz=timezone.utc) - timedelta(days=1)
    return filter_start_time


def get_filter_end_time(request):
    if 'timeFilter' in request.GET and request.GET['timeFilter'] == 'customRange':
        filter_end_time = parse_uri_datetime(request.GET['to'])
    else:
        filter_end_time = datetime.now(tz=timezone.utc)

    return filter_end_time


# def prepare_data_as_csv(readings):
#     column_headings = get_column_headings(readings)
#     csv_header = ','.join(column_headings) + '\n'
#     csv_data = '\n'.join(reading_to_csv_row(reading, column_headings) for reading in readings)
#
#     return csv_header + csv_data


# def reading_to_csv_row(reading, columns):
#     return ','.join(str(reading[column]) for column in columns)


def prepare_data_for_canvasjs(trace_data):
    trace_pyjsons = []

    for trace in trace_data:

        if trace['type'] == 'temperature':
            line_color = 'IndianRed'
            axis_y_type = 'primary'
            x_value_format_string = 'YYYY-MM-DD HH:mm:ss'
            y_value_format_string = '#.#°C'
        elif trace['type'] == 'humidity':
            line_color = 'CadetBlue'
            axis_y_type = 'secondary'
            x_value_format_string = 'YYYY-MM-DD HH:mm:ss'
            y_value_format_string = "#'%'"
        else:
            line_color = 'Black'
            axis_y_type = 'primary'
            x_value_format_string = 'YYYY-MM-DD HH:mm:ss'
            y_value_format_string = '#'

        # Add the trace definition
        trace_pyjsons.append({
            "type": "line",
            "color": line_color,
            "axisYType": axis_y_type,
            "name": f'{trace["sensor_name"]} ({trace["type"]})',
            "showInLegend": True,
            "markerSize": 0,
            "xValueFormatString": x_value_format_string,
            "yValueFormatString": y_value_format_string,
            "xValueType": "dateTime",
            "dataPointsType": trace['type'],
            "dataPoints": trace['data']
        })

    trace_json = json_dumps(trace_pyjsons)

    return trace_json


def get_data_lists(raw_data, smoothing=False):
    def is_not_outlier(datum, data_lists_by_sensorid):

        if not smoothing:
            return True

        datum_stale_time = timedelta(hours=6)
        thresholds = {
            'temperature': 0.2,
            'humidity': 1.0,
        }

        try:
            previous_valid_timestamp = parse_uri_datetime(
                data_lists_by_sensorid[datum['unique_sensor_name']]['data'][-1]['x'])
            previous_valid_value = data_lists_by_sensorid[datum['unique_sensor_name']]['data'][-1]['y']
            is_outlier = abs(previous_valid_value - json_safe(datum['value'])) > thresholds[
                get_type_mappings()[datum['type_id']]]
            previous_value_is_old = datum['timestamp'] - previous_valid_timestamp > datum_stale_time
            return (not is_outlier) or previous_value_is_old
        except IndexError:
            return True

    data_lists = []
    data_lists_by_sensorid = {}

    for datum in raw_data:
        if datum['unique_sensor_name'] not in data_lists_by_sensorid:
            data_lists.append(
                get_structured_data_object(datum, get_type_mappings()))
            data_lists_by_sensorid.update({datum['unique_sensor_name']: data_lists[-1]})

        if is_not_outlier(datum, data_lists_by_sensorid):
            data_lists_by_sensorid[datum['unique_sensor_name']]['data'].append({  # todo: turn datalist into a class
                'x': datetime_to_js_epoch(datum['timestamp']),
                'y': json_safe(datum['value'])
            })

    return data_lists


def json_safe(object):
    import decimal
    if isinstance(object, decimal.Decimal):
        return float(object)
    else:
        return object


def get_type_mappings():
    return ('none', 'temperature', 'humidity')  # todo: generate type mappings dynamically


def get_structured_data_object(datum, type_mappings):
    return {
        'sensor_name': datum['unique_sensor_name'].split(';')[0],
        'type': type_mappings[datum['type_id']],
        'data': []
    }


def get_history(request):  # todo: move all the get_data_lists() logic to the models where it belongs
    device_name = request.GET['device']
    client_tz_offset = request.GET['clientTzOffset']

    datetime_range = DatetimeRangePicker(request.POST)
    datetime_range.is_valid()
    datetime_range = datetime_range.get_datetime_range()

    history_start = datetime_range['from'] + timedelta(minutes=int(client_tz_offset))
    history_end = datetime_range['to'] + timedelta(minutes=int(client_tz_offset))
    history_duration = history_end - history_start

    requested_format = 'canvas_js' if 'format' not in request.GET else request.GET['format']

    # Downsample the queryset to avoid long fetch and page-load times
    downsampled_queryset = downsample(
        SensorDatum.objects.filter(sensor__datalogger__device_name=device_name,
                                   timestamp__gte=history_start,
                                   timestamp__lte=history_end)
    ).order_by('timestamp', 'sensor_id', 'type_id')

    if requested_format == 'csv':
        # response_str = prepare_data_as_csv(get_data_lists(raw_data))
        return HttpResponse('CSV Export Temporarily Deprecated')
    elif requested_format == 'canvas_js':
        smoothing = True if history_duration > timedelta(days=3) else False
        return HttpResponse(prepare_data_for_canvasjs(get_data_lists(downsampled_queryset.values(), smoothing)))
    else:
        return HttpResponse('invalid request format')


def request_server_time(request):
    return HttpResponse(str(datetime.utcnow().timestamp()).split('.')[0])


def utc_to_local(utc_dt):
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=None)


UPPER_DATA_COUNT_LIMIT = 2000


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


def newview(request):
    # Get device name
    device_name = request.GET['device']

    context = {
        'device_name': device_name,
        'modal_datetime_range_picker': DatetimeRangePicker(initial={
            'from_date': datetime.today().strftime('%m/%d/%Y'),
            'from_hours': 12,
            'from_minutes': 00,
            'from_is_pm': False,
            'to_date': (datetime.today() + timedelta(days=1)).strftime('%m/%d/%Y'),
            'to_hours': 12,
            'to_minutes': 00,
            'to_is_pm': False,
        })
    }

    return render(request, 'pulogger/new_view.html', context)


similar_value_update_lockout = timedelta(minutes=29, seconds=50)
different_value_update_lockout = timedelta(seconds=50)
data_update_hysteresis = {
    'temperature': 0.2,
    'humidity': 2.0,
}


def submit_data(request):  # todo: refactor this fat-ass view
    device = request.GET['device']
    sensor_names = request.GET['sensors'].split(',')
    datum_types = request.GET['types'].split(',')
    datum_values = request.GET['values'].split(',')
    timestamp = datetime.utcfromtimestamp(int(request.GET['timestamp'])).replace(tzinfo=timezone(timedelta()))
    data = ({'sensor_name': sensor_names[idx], 'type': datum_types[idx], 'value': Decimal(datum_values[idx])} for idx in
            range(0, len(sensor_names)))
    submission_ip = "1.1.1.1"  # placeholder

    context = {
        'success': True,
        'response': ''
    }

    for datum in data:
        try:
            sensor = Sensor.objects.get(
                sensor_name=datum['sensor_name'],
                datalogger__device_name=device
            )

            # Get the datumtype id so we can generate the full 'sensor_name;sensor_id_;type_id' string
            datum_type = SensorModelDatumType.objects.filter(sensor__type=sensor.type.type,
                                                             datum_type__description=datum['type']).first()

            # Check that a valid sensor exists for the parameters provided, else throw exception
            if not datum_type:
                raise DataTypeMismatchError('Sensor type {} cannot measure {}.'.format(sensor.type.type, datum['type']))

            # Get the (indexed, unique) full-form sensor name and most recent reading
            unique_sensor_name = f'{sensor.sensor_name};{sensor.id};{datum_type.id}'
            most_recent_reading = SensorDatum.objects.filter(unique_sensor_name=unique_sensor_name).order_by(
                '-timestamp').first()

            # if the difference from last logged value exceeds hysteresis, or last log happened sufficiently long ago
            if not most_recent_reading \
                    or abs(datum['value'] - most_recent_reading.value) > data_update_hysteresis[datum['type']] \
                    and timestamp > (
                    most_recent_reading.timestamp + different_value_update_lockout) \
                    or timestamp > (
                    most_recent_reading.timestamp + similar_value_update_lockout):
                # log the datum
                new_datum = SensorDatum(
                    submission_ip=submission_ip,
                    timestamp=timestamp,
                    value=datum['value'],
                    sensor_id=sensor.pk,
                    type_id=DatumType.objects.get(description=datum['type']).pk,
                )

                new_datum.full_clean()
                new_datum.save()

                context['response'] += f'Successfully logged {str(new_datum)}<br>'
            else:
                context['success'] = False
                context['response'] += 'Datum ignored: Value similar to recently-logged previous datum.<br>'

        except ValidationError:
            context['success'] = False
            context['response'] += 'Error: Submitted datum failed validation.<br>'

        except ObjectDoesNotExist:
            context['success'] = False
            context['response'] += 'Error: No such device, or no such sensor named {} attached to device.<br>'.format(
                datum[
                    "sensor_name"])

        except DataTypeMismatchError as err:
            context['success'] = False
            context['response'] += f'{err.message}<br>'

    return render(request, 'pulogger/submitDatumResponse.html', context)


def index(request):
    return render(request, 'pulogger/index.html', None)
