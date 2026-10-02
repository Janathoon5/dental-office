import datetime
from django import forms
from django.utils import timezone
from dental_office.providers import ProviderChoiceField, limit_to_providers, provider_label
from .models import Appointment, AppointmentRequest

OFFICE_OPEN  = datetime.time(8, 0)   # 8:00 AM
OFFICE_CLOSE = datetime.time(19, 0)  # 7:00 PM


class AppointmentForm(forms.ModelForm):
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
        limit_to_providers(self.fields['dentist'], current=self.instance.dentist if self.instance.pk else None)
        self.fields['dentist'].required = False
        if not self.instance.pk:
            self.fields['date'].widget.attrs['min'] = timezone.localdate().isoformat()
        self.fields['start_time'].widget.attrs['min'] = OFFICE_OPEN.strftime('%H:%M')
        self.fields['start_time'].widget.attrs['max'] = OFFICE_CLOSE.strftime('%H:%M')

    def clean_date(self):
        # New bookings must be today or later, and so must a move to a new
        # date. Past appointments can still be updated (marked completed or
        # no-show, notes added) as long as their date stays the same.
        date = self.cleaned_data.get('date')
        unchanged = self.instance.pk and date == self.instance.date
        if date and date < timezone.localdate() and not unchanged:
            raise forms.ValidationError("New appointments can't be booked on a past date.")
        return date

    def clean_start_time(self):
        time = self.cleaned_data.get('start_time')
        if time:
            if time < OFFICE_OPEN:
                raise forms.ValidationError("The office opens at 8:00 AM. Please choose a later time.")
            if time > OFFICE_CLOSE:
                raise forms.ValidationError("The office closes at 7:00 PM. Please choose an earlier time.")
        return time

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
                    name = provider_label(dentist).split(' (')[0]
                    raise forms.ValidationError(
                        f"{name} already has an appointment at "
                        f"{appt.start_time.strftime('%I:%M %p').lstrip('0')} on this date. "
                        f"Choose another time or provider."
                    )
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
        self.fields['preferred_time'].widget.attrs['min'] = OFFICE_OPEN.strftime('%H:%M')
        self.fields['preferred_time'].widget.attrs['max'] = OFFICE_CLOSE.strftime('%H:%M')

    def clean_preferred_date(self):
        date = self.cleaned_data.get('preferred_date')
        if date and date < timezone.localdate():
            raise forms.ValidationError("Please choose a future date for your appointment.")
        return date

    def clean_preferred_time(self):
        time = self.cleaned_data.get('preferred_time')
        if time:
            if time < OFFICE_OPEN:
                raise forms.ValidationError("The office opens at 8:00 AM. Please choose a later time.")
            if time > OFFICE_CLOSE:
                raise forms.ValidationError("The office closes at 7:00 PM. Please choose an earlier time.")
        return time
