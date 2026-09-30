from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
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


class AppointmentRequestManager(models.Manager):
    def expire_stale(self):
        return self.filter(
            status='pending', preferred_date__lt=timezone.localdate()
        ).update(status='expired')


class AppointmentRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('declined', 'Declined'),
        ('expired', 'Expired'),
    ]

    objects = AppointmentRequestManager()

    patient = models.ForeignKey(
        'patients.Patient', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='appointment_requests'
    )
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


class RecallNotice(models.Model):
    """One row per recall email attempt. A patient's recall is identified by
    its due date, so a 'sent' row for (patient, due_date) means that cycle's
    email already went out and the daily job won't send it again."""
    STATUS_CHOICES = ReminderLog.STATUS_CHOICES

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='recall_notices')
    due_date = models.DateField()
    sent_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='sent')
    recipient_email = models.EmailField(blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-sent_at']

    def __str__(self):
        return f"Recall for {self.patient} (due {self.due_date}) — {self.status}"


class ScheduledJobRun(models.Model):
    """One run of the daily email job (send_daily_emails), so staff can see
    that automatic emails are actually going out."""
    ran_at = models.DateTimeField(auto_now_add=True)
    succeeded = models.BooleanField(default=True)
    summary = models.TextField(blank=True)

    class Meta:
        ordering = ['-ran_at']

    def __str__(self):
        return f"Daily emails {self.ran_at:%Y-%m-%d %H:%M} — {'ok' if self.succeeded else 'failed'}"

    @classmethod
    def status(cls):
        """Latest run, and whether it's overdue (the job runs once a day)."""
        from django.utils import timezone
        import datetime
        last = cls.objects.first()
        overdue = last is not None and timezone.now() - last.ran_at > datetime.timedelta(hours=26)
        return {'last': last, 'overdue': overdue}
