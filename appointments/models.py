from django.db import models
from django.contrib.auth.models import User
from patients.models import Patient


class Appointment(models.Model):
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No Show'),
    ]

    TYPE_CHOICES = [
        ('checkup', 'Checkup'),
        ('cleaning', 'Cleaning'),
        ('filling', 'Filling'),
        ('extraction', 'Extraction'),
        ('consultation', 'Consultation'),
        ('other', 'Other'),
    ]

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='appointments')
    dentist = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='appointments')
    date = models.DateField()
    start_time = models.TimeField()
    duration_minutes = models.PositiveIntegerField(default=60)
    appointment_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='checkup')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date', 'start_time']

    def __str__(self):
        return f"{self.patient} — {self.date} {self.start_time}"


class AppointmentRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('declined', 'Declined'),
    ]

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    preferred_date = models.DateField()
    preferred_time = models.TimeField()
    appointment_type = models.CharField(max_length=20, choices=Appointment.TYPE_CHOICES, default='checkup')
    message = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f"{self.first_name} {self.last_name} — {self.preferred_date}"


class ReminderLog(models.Model):
    STATUS_CHOICES = [
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('no_email', 'No Email'),
    ]

    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name='reminders')
    sent_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='sent')
    recipient_email = models.EmailField(blank=True)
    days_before = models.PositiveIntegerField(default=1)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-sent_at']

    def __str__(self):
        return f"Reminder for {self.appointment} — {self.status}"
