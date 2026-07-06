from django import forms
from datetime import date, time
from django.contrib.auth.forms import SetPasswordForm as _SetPasswordForm
from appointments.models import AppointmentRequest
from patients.models import Patient

_ctrl = {'class': 'form-control'}
_select = {'class': 'form-select'}

# Office hours by weekday (0=Monday … 6=Sunday). Missing key = closed.
OFFICE_HOURS = {
    0: (time(8, 0), time(17, 0)),
    1: (time(8, 0), time(17, 0)),
    2: (time(8, 0), time(17, 0)),
    3: (time(8, 0), time(17, 0)),
    4: (time(8, 0), time(17, 0)),
    5: (time(8, 0), time(13, 0)),
}
_DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def _fmt(t):
    return t.strftime('%I:%M %p').lstrip('0')


class AppointmentRequestForm(forms.ModelForm):
    preferred_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date', **_ctrl}))
    preferred_time = forms.TimeField(widget=forms.TimeInput(attrs={'type': 'time', **_ctrl}))

    class Meta:
        model = AppointmentRequest
        fields = ['preferred_date', 'preferred_time', 'appointment_type', 'message']
        widgets = {
            'appointment_type': forms.Select(attrs=_select),
            'message': forms.Textarea(attrs={**_ctrl, 'rows': 3, 'placeholder': 'Any details or concerns...'}),
        }
        labels = {
            'message': 'Additional notes (optional)',
        }

    def clean_preferred_date(self):
        d = self.cleaned_data.get('preferred_date')
        if d and d < date.today():
            raise forms.ValidationError("Please choose a future date.")
        return d

    def clean(self):
        cleaned_data = super().clean()
        preferred_date = cleaned_data.get('preferred_date')
        preferred_time = cleaned_data.get('preferred_time')

        if preferred_date and preferred_time:
            weekday = preferred_date.weekday()
            day_name = _DAY_NAMES[weekday]
            hours = OFFICE_HOURS.get(weekday)
            if hours is None:
                self.add_error('preferred_date',
                    f'The office is closed on {day_name}s. '
                    f'Please choose a weekday or Saturday.')
            else:
                open_t, close_t = hours
                if not (open_t <= preferred_time < close_t):
                    self.add_error('preferred_time',
                        f'On {day_name}s, office hours are {_fmt(open_t)} – {_fmt(close_t)}. '
                        f'Please pick a time within those hours.')

        return cleaned_data


class PatientProfileForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = ['phone', 'email', 'address']
        widgets = {
            'phone': forms.TextInput(attrs=_ctrl),
            'email': forms.EmailInput(attrs=_ctrl),
            'address': forms.Textarea(attrs={**_ctrl, 'rows': 2}),
        }


class InviteSetPasswordForm(_SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
