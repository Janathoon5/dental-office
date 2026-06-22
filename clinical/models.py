from django.db import models
from django.contrib.auth.models import User
from patients.models import Patient
from appointments.models import Appointment


class TreatmentRecord(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='treatment_records')
    appointment = models.OneToOneField(Appointment, on_delete=models.SET_NULL, null=True, blank=True, related_name='treatment_record')
    dentist = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='treatment_records')
    date = models.DateField()
    procedure = models.CharField(max_length=200)
    tooth_number = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.patient} — {self.procedure} ({self.date})"


class TreatmentPlan(models.Model):
    STATUS_CHOICES = [
        ('proposed', 'Proposed'),
        ('accepted', 'Accepted'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
    ]

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='treatment_plans')
    title = models.CharField(max_length=200)
    created_date = models.DateField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='proposed')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_date']

    def __str__(self):
        return f"{self.patient} — {self.title}"

    def total_cost(self):
        return sum(item.estimated_cost for item in self.items.all())


class TreatmentPlanItem(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
    ]

    plan = models.ForeignKey(TreatmentPlan, on_delete=models.CASCADE, related_name='items')
    procedure = models.CharField(max_length=200)
    tooth_number = models.CharField(max_length=20, blank=True)
    estimated_cost = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    def __str__(self):
        return self.procedure
