from django import forms
from django.contrib.auth.forms import SetPasswordForm as _SetPasswordForm
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from appointments.models import AppointmentRequest
from patients.models import Patient
from .validators import validate_office_hours

_ctrl = {'class': 'form-control'}
_select = {'class': 'form-select'}


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
        # localdate(), not date.today(): the server runs UTC, so after 8pm
        # Eastern date.today() is already tomorrow and would reject a
        # request for what is still today at the office.
        if d and d < timezone.localdate():
            raise forms.ValidationError("Please choose a future date.")
        return d

    def clean(self):
        cleaned_data = super().clean()
        preferred_date = cleaned_data.get('preferred_date')
        preferred_time = cleaned_data.get('preferred_time')

        try:
            validate_office_hours(preferred_date, preferred_time)
        except DjangoValidationError as e:
            for field, messages in e.message_dict.items():
                for msg in messages:
                    self.add_error(field, msg)

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
