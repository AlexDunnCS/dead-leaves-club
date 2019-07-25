from django import forms
from datetime import datetime

BOOL_CHOICES = (
    (False, 'AM'),
    (True, 'PM')
)


def getHourChoices():
    choices = []
    for idx in range(1, 13):
        choices.append((idx, ("0" + str(idx))[-2:]))
    return choices


def getMinuteChoices():
    choices = []
    for idx in range(0, 60, 15):
        choices.append((idx, ("0" + str(idx))[-2:]))
    return choices


class DatetimeRangePicker(forms.Form):
    from_date = forms.DateField(label='', widget=forms.TextInput(
        attrs={
            'class': 'from date datepicker'
        }
    ))

    from_hours = forms.IntegerField(label='', widget=forms.Select(
        choices=getHourChoices(),
        attrs={
            'class': 'from hours'
        }
    ))

    from_minutes = forms.IntegerField(label=':', widget=forms.Select(
        choices=getMinuteChoices(),
        attrs={
            'class': 'from minutes'
        }
    ))

    from_is_pm = forms.BooleanField(required=False, label='', widget=forms.Select(
        choices=BOOL_CHOICES,
        attrs={
            'class': 'from is-pm'
        }
    ))

    to_date = forms.DateField(label='', widget=forms.TextInput(
        attrs={
            'class': 'to date datepicker'
        }
    ))

    to_hours = forms.IntegerField(label='', widget=forms.Select(
        choices=getHourChoices(),
        attrs={
            'class': 'to hours'
        }
    ))

    to_minutes = forms.IntegerField(label=':', widget=forms.Select(
        choices=getMinuteChoices(),
        attrs={
            'class': 'to minutes'
        }
    ))

    to_is_pm = forms.BooleanField(required=False, label='', widget=forms.Select(
        choices=BOOL_CHOICES,
        attrs={
            'class': 'to is-pm'
        }
    ))

    def convert12hrTo24hr(self, hour, isPm):
        if hour == 12:
            hour = 0
        return hour + 12 if isPm else hour

    def get_datetime_range(self):
        datetime_range = {}
        data = self.cleaned_data
        for prefix in ('from', 'to'):
            hours = self.convert12hrTo24hr(data.get(f'{prefix}_hours'), data.get(f'{prefix}_is_pm'))
            minutes = data.get(f'{prefix}_minutes')

            value = datetime(
                data.get(f'{prefix}_date').year,
                data.get(f'{prefix}_date').month,
                data.get(f'{prefix}_date').day,
                hours,
                minutes,
            )

            datetime_range.update({prefix: value})

        return datetime_range
