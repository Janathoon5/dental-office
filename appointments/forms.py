import datetime
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from dental_office.providers import ProviderChoiceField, limit_to_providers, provider_name
from patient_portal.validators import office_hours_problem, validate_office_hours
from .models import Appointment, AppointmentRequest

MIN_DURATION = 5      # minutes
MAX_DURATION = 240    # 4 hours; longer work is booked as more than one visit
BOOKING_HORIZON = datetime.timedelta(days=2 * 365)


class AppointmentForm(forms.ModelForm):
    duration_minutes = forms.IntegerField(
        min_value=MIN_DURATION, max_value=MAX_DURATION, initial=60,
        widget=forms.NumberInput(attrs={'step': 5}),
        error_messages={
            'min_value': f'A visit has to be at least {MIN_DURATION} minutes long.',
            'max_value': f'A visit can be at most {MAX_DURATION // 60} hours long. Book longer work as two visits.',
        },
    )
    # Shown once the chosen time turns out to be outside office hours.
    outside_hours_ok = forms.BooleanField(required=False)

    class Meta:
        model = Appointment
        fields = ['patient', 'dentist', 'date', 'start_time', 'duration_minutes', 'appointment_type', 'status', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
        field_classes = {'dentist': ProviderChoiceField}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outside_hours = None
        limit_to_providers(self.fields['dentist'], current=self.instance.dentist if self.instance.pk else None)
        self.fields['dentist'].required = False
        today = timezone.localdate()
        if not self.instance.pk:
            self.fields['date'].widget.attrs['min'] = today.isoformat()
        self.fields['date'].widget.attrs['max'] = (today + BOOKING_HORIZON).isoformat()

    def _date_unchanged(self, date):
        return bool(self.instance.pk) and date == self.instance.date

    def clean_date(self):
        # New bookings must be today or later, and so must a move to a new
        # date. Past appointments can still be updated (marked completed or
        # no-show, notes added) as long as their date stays the same.
        date = self.cleaned_data.get('date')
        if not date or self._date_unchanged(date):
            return date
        today = timezone.localdate()
        if date < today:
            raise forms.ValidationError("New appointments can't be booked on a past date.")
        if date > today + BOOKING_HORIZON:
            raise forms.ValidationError(
                f'That date is more than 2 years away ({date.year}). Check the year.'
            )
        return date

    def _time_changed(self, date, start_time, duration):
        if not self.instance.pk:
            return True
        return (date, start_time, duration) != (self.instance.date, self.instance.start_time,
                                                self.instance.duration_minutes)

    def clean(self):
        cleaned_data = super().clean()
        dentist = cleaned_data.get('dentist')
        date = cleaned_data.get('date')
        start_time = cleaned_data.get('start_time')
        duration = cleaned_data.get('duration_minutes')
        if dentist and date and start_time and duration:
            start_dt = datetime.datetime.combine(date, start_time)
            end_dt = start_dt + datetime.timedelta(minutes=duration)
            conflicts = Appointment.objects.filter(dentist=dentist, date=date).exclude(status='cancelled')
            if self.instance.pk:
                conflicts = conflicts.exclude(pk=self.instance.pk)
            for appt in conflicts:
                other_start = datetime.datetime.combine(date, appt.start_time)
                other_end = other_start + datetime.timedelta(minutes=appt.duration_minutes)
                if start_dt < other_end and other_start < end_dt:
                    raise forms.ValidationError(
                        f"{provider_name(dentist)} already has an appointment at "
                        f"{appt.start_time.strftime('%I:%M %p').lstrip('0')} on this date. "
                        f"Choose another time or provider."
                    )
        # Outside office hours is allowed (emergencies, a late patient) but
        # staff have to say so, which catches AM/PM and date typos.
        if date and start_time and duration and self._time_changed(date, start_time, duration):
            self.outside_hours = office_hours_problem(date, start_time, duration)
            if self.outside_hours and not cleaned_data.get('outside_hours_ok'):
                raise forms.ValidationError(f'{self.outside_hours} Tick "Book anyway" to keep this time.')
        return cleaned_data


class AppointmentRequestForm(forms.ModelForm):
    class Meta:
        model = AppointmentRequest
        fields = ['first_name', 'last_name', 'phone', 'email', 'preferred_date', 'preferred_time', 'appointment_type', 'message']
        widgets = {
            'preferred_date': forms.DateInput(attrs={'type': 'date'}),
            'preferred_time': forms.TimeInput(attrs={'type': 'time'}),
            'message': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Any additional info or questions...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['preferred_date'].widget.attrs['min'] = timezone.localdate().isoformat()

    def clean_preferred_date(self):
        date = self.cleaned_data.get('preferred_date')
        if date and date < timezone.localdate():
            raise forms.ValidationError("Please choose a future date for your appointment.")
        return date

    def clean(self):
        # Same office-hours rule as the patient portal and the mobile app.
        cleaned_data = super().clean()
        try:
            validate_office_hours(cleaned_data.get('preferred_date'), cleaned_data.get('preferred_time'))
        except ValidationError as e:
            for field, errors in e.message_dict.items():
                for error in errors:
                    self.add_error(field, error)
        return cleaned_data
