from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from datetime import datetime, timedelta, timezone

from pulogger.forms import DatetimeRangePicker
from math import floor, ceil

from .models import Datalogger, SensorModel, Sensor, DatumType, SensorModelDatumType, SensorDatum


class DataTypeMismatchError(Exception):
    def __init__(self, message):
        self.message = message


def parse_uri_datetime(ms_since_epoch):
    ts_epoch = int(ms_since_epoch) / 1000
    return datetime.fromtimestamp(ts_epoch)


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


def get_filter_start_time(request):
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
        elif filter_type == 'customRange':
            filter_start_time = parse_uri_datetime(request.GET['from'])
        else:
            filter_start_time = datetime.now() - timedelta(days=1)
    else:
        filter_start_time = datetime.now() - timedelta(days=1)
    return filter_start_time


def get_filter_end_time(request):
    if 'timeFilter' in request.GET and request.GET['timeFilter'] == 'customRange':
        filter_end_time = parse_uri_datetime(request.GET['to'])
    else:
        filter_end_time = datetime.now()

    return filter_end_time


def prepare_data_as_csv(data, column_headers=('timestamp', 'temperature', 'relative_humidity')):
    csv_header = ','.join(column_headers) + '\n'

    csv_data = list(data)
    for idx, row in enumerate(csv_data):
        row[0] = row[0].strftime('%Y-%m-%d %H:%M:%S')
        csv_data[idx] = ','.join(str(x) for x in row)

    csv_data = '\n'.join(csv_data)

    return csv_header + csv_data


def get_history(request):
    device_name = request.GET['device']
    client_tz_offset = request.GET['clientTzOffset']

    datetime_range = DatetimeRangePicker(request.POST)
    datetime_range.is_valid()
    datetime_range = datetime_range.get_datetime_range()

    history_start = datetime_range['from'] + timedelta(minutes=int(client_tz_offset))
    history_end = datetime_range['to'] + timedelta(minutes=int(client_tz_offset))

    # history_start = datetime.now() - timedelta(days=1)
    # history_end = datetime.now()

    requested_format = 'canvas_js' if 'format' not in request.GET else request.GET['format']

    device = Datalogger.objects.get(device_name=device_name)

    # Get sensors attached to device, along with models and datum-types a sensor provides
    sensors = Sensor.objects.filter(datalogger=device).order_by('pk').select_related('type')
    sensor_models = sensors.values_list('type', flat=True)  # get all models of sensor used by this controller
    sensor_model_datum_types = list(SensorModelDatumType.objects.filter(sensor__in=sensor_models).order_by('sensor',
                                                                                                           'datum_type'))  # get all datatypes relating to all models of sensor used

    # assign each trace (sensor/datum_type combination) an index for the tuples (zero is used for time/x-axis)
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

    # # Get all data for the selected device during the given period
    # bulk_queryset = SensorDatum.objects.filter(sensor__datalogger__device_name=device_name,
    #                                            timestamp__gte=get_filter_start_time(request),
    #                                            timestamp__lte=get_filter_end_time(request))

    # Downsample the queryset to avoid long fetch and page-load times
    downsampled_queryset = downsample(
        SensorDatum.objects.filter(sensor__datalogger__device_name=device_name,
                                   timestamp__gte=history_start,
                                   timestamp__lte=history_end)
    ).order_by('timestamp', 'sensor_id', 'type_id')

    # Process data into timestamp-grouped tuples accessible by chart_trace_index ([0] is timestamp)
    raw_data = downsampled_queryset.values()
    structured_data = []

    # Add all the data to the prepared-data list
    for datum in raw_data:
        # If it's necessary to create a new tuple, create it, with None-valued placeholders for each value
        # Assumes any values within 1 second of each other are functionally at the same time
        if len(structured_data) == 0 or abs(datum['timestamp'] - structured_data[-1][0]) > timedelta(seconds=1):
            structured_data.append([datum['timestamp']])
            structured_data[-1].extend([None] * len(chart_traces))

        # Store the datum in the appropriate element of the most-recent tuple
        structured_data[-1][chart_trace_indices[get_chart_trace_id(datum['sensor_id'], datum['type_id'])]] = datum[
            'value']

    # Construct a list of column labels based on the sensor name and value type (temp, humidity)
    column_labels = ['Time']
    column_types = ["datetime"]
    for chart_trace in chart_traces:
        column_labels.append(chart_trace['chart_trace_name'])
        column_types.append(chart_trace['datum_type'])

    if requested_format == 'csv':
        response_str = prepare_data_as_csv(structured_data)
    elif requested_format == 'canvas_js':
        response_str = prepare_data_for_canvasjs(column_labels, column_types, structured_data)
    else:
        response_str = {'invalid request format'}

    return HttpResponse(response_str)


def request_server_time(request):
    return HttpResponse(str(datetime.utcnow().timestamp()).split('.')[0])


def prepare_data_for_canvasjs(column_labels, column_types, data):
    trace_jsons = []

    for idx, column_label in enumerate(column_labels[1:], start=1):
        column_type = column_types[idx]
        if column_type == 'temperature':
            line_color = 'IndianRed'
            axis_y_type = 'primary'
            x_value_format_string = 'YYYY-MM-DD HH:mm:ss'
            y_value_format_string = '#.#°C'
        elif column_type == 'humidity':
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
        trace_jsons.append(f'''
{{
    "type":"line",
    "color":"{line_color}",
    "axisYType": "{axis_y_type}",
    "name": "{column_label}",
    "showInLegend": true,
    "markerSize": 0,
    "xValueFormatString": "{x_value_format_string}",
    "yValueFormatString": "{y_value_format_string}",
    "xValueType": "dateTime",
    "dataPoints": [''')

    for row_idx, row in enumerate(data):
        # For every datum index in every data row
        for trace_data_idx, trace_datum in enumerate(row[1:], start=1):
            trace_json_idx = trace_data_idx - 1

            # If the datum has a value
            if row[trace_data_idx] != None:
                # If it's not the first datum for a given trace, insert a comma
                if not trace_jsons[trace_json_idx].endswith('['):
                    trace_jsons[trace_json_idx] += ','
                # then add the datum
                trace_jsons[trace_json_idx] += f'''{{ "x": {datetime_to_js_epoch(row[0])}, "y": {row[
                    trace_data_idx]} }}'''

    trace_jsons = [json + ']}\n' for json in trace_jsons]

    prepared_json = '[' + ','.join(trace_jsons) + '\n]'
    # prepared_json = '[' + trace_jsons[0] + '\n]'

    return prepared_json


def utc_to_local(utc_dt):
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=None)


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


# def simpleview(request):
#     device_name = request.GET['device']
#     device = Datalogger.objects.get(device_name=device_name)
#
#     sensors = Sensor.objects.filter(datalogger=device).order_by('pk').select_related('type')
#     sensor_count = len(sensors)  # should be no worse than count() since already-evaluated and cached.  todo: confirm
#     sensor_models = sensors.values_list('type', flat=True)  # get all models of sensor used by this controller
#     sensor_model_datum_types = list(SensorModelDatumType.objects.filter(sensor__in=sensor_models).order_by('sensor',
#                                                                                                      'datum_type'))  # get all datatypes relating to all models of sensor used
#
#     # assign each trace (sensor/datum_type combination) an indice for the tuples (zero is used for time/x-axis)
#     bulk_queryset = SensorDatum.objects.filter(sensor__datalogger__device_name=device_name,
#                                                timestamp__gte=get_filter_start_time(request),
#                                                timestamp__lte=get_filter_end_time(request))
#     downsampled_queryset = downsample(
#         SensorDatum.objects.filter(sensor__datalogger__device_name=device_name,
#                                    timestamp__gte=get_filter_start_time(request),
#                                    timestamp__lte=get_filter_end_time(request))
#     ).order_by('timestamp', 'sensor_id', 'type_id')
#
#     chart_traces = []
#     chart_trace_indices = {}
#     next_free_idx = 1
#     for sensor in sensors:
#         for sensor_model_datum_type in sensor_model_datum_types:
#             if sensor_model_datum_type.sensor == sensor.type:
#                 chart_trace_name = get_chart_trace_name(sensor.sensor_name,
#                                                         sensor_model_datum_type.datum_type.description)
#                 chart_traces.append(
#                     {'sensor': sensor.sensor_name, 'datum_type': sensor_model_datum_type.datum_type.description,
#                                      'chart_trace_name': chart_trace_name})
#                 chart_trace_indices.update(
#                     {get_chart_trace_id(sensor.id, sensor_model_datum_type.datum_type_id): next_free_idx})
#                 next_free_idx += 1
#
#     # process data into timestamp-grouped tuples accessible by chart_trace_index ([0] is timestamp)
#     raw_data = downsampled_queryset.values()
#     data = []
#
#     for datum in raw_data:
#         if len(data) == 0 or datum['timestamp'] != data[-1][0]:
#             data.append([datum['timestamp']])
#             data[-1].extend([None] * len(chart_traces))
#
#         data[-1][chart_trace_indices[get_chart_trace_id(datum['sensor_id'], datum['type_id'])]] = datum['value']
#
#     column_labels = ['Time']
#     column_types = ["datetime"]
#     for chart_trace in chart_traces:
#         column_labels.append(chart_trace['chart_trace_name'])
#         column_types.append("number")
#
#     gchart_json = prepare_data_for_gchart(column_labels, column_types, data)
#
#     context = {
#         'device': device_name,
#         'sensor_count': sensor_count,
#         'sensor_indices': chart_trace_indices,
#         'gchart_json': gchart_json,
#     }
#
#     return render(request, 'pulogger/simpleTimeSeriesView.html', context)


def submit_data(request):
    device = request.GET['device']
    sensor_names = request.GET['sensors'].split(',')
    datum_types = request.GET['types'].split(',')
    datum_values = request.GET['values'].split(',')
    timestamp = datetime.utcfromtimestamp(int(request.GET['timestamp']))
    data = ({'sensor_name': sensor_names[idx], 'type': datum_types[idx], 'value': datum_values[idx]} for idx in
            range(0, len(sensor_names)))
    submission_ip = "1.1.1.1"  # placeholder

    context = {
        'success': True,
        'response': ''
    }

    for datum in data:
        try:
            # Check that a valid sensor exists for the parameters provided, else throw exception
            sensor = Sensor.objects.get(
                sensor_name=datum['sensor_name'],
                datalogger__device_name=device
            )

            if not SensorModelDatumType.objects.filter(sensor__type=sensor.type.type,
                                                       datum_type__description=datum['type']).exists():
                raise DataTypeMismatchError('Sensor type {} cannot measure {}.'.format(sensor.type.type, datum['type']))

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