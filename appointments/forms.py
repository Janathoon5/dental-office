import datetime
from django import forms
from django.contrib.auth.models import User
from django.utils import timezone
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['dentist'].queryset = User.objects.filter(staff_profile__role__in=['dentist', 'hygienist'])
        self.fields['dentist'].required = False
        self.fields['date'].widget.attrs['min'] = timezone.localdate().isoformat()
        self.fields['start_time'].widget.attrs['min'] = OFFICE_OPEN.strftime('%H:%M')
        self.fields['start_time'].widget.attrs['max'] = OFFICE_CLOSE.strftime('%H:%M')

    def clean_date(self):
        date = self.cleaned_data.get('date')
        if date and date < timezone.localdate():
            raise forms.ValidationError("Appointments cannot be booked on past dates.")
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
                    raise forms.ValidationError(
                        f"{dentist.get_full_name() or dentist.username} already has an appointment "
                        f"at {appt.start_time.strftime('%I:%M %p')} on this date."
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
