from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth.models import User
from encrypted_model_fields.fields import EncryptedTextField
from dental_office.mixins import SoftDeleteModel
from patients.models import Patient
from appointments.models import Appointment


class TreatmentRecord(SoftDeleteModel):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='treatment_records')
    appointment = models.OneToOneField(Appointment, on_delete=models.SET_NULL, null=True, blank=True, related_name='treatment_record')
    dentist = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='treatment_records')
    date = models.DateField()
    procedure = models.CharField(max_length=200)
    tooth_number = models.CharField(max_length=20, blank=True)
    notes = EncryptedTextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ['-date']

    def __str__(self):
        return f"{self.patient} — {self.procedure} ({self.date})"


class TreatmentPlan(SoftDeleteModel):
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
    notes = EncryptedTextField(blank=True)

    class Meta(SoftDeleteModel.Meta):
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


class ToothCondition(models.Model):
    """The current state of one tooth, using Universal numbering (1-32).
    A tooth with no row is healthy — setting a tooth back to healthy deletes
    its row. Changes are tracked by auditlog rather than soft delete, since
    only the latest state matters for the chart."""
    CONDITION_CHOICES = [
        ('decay', 'Decay / Cavity'),
        ('filling', 'Filling'),
        ('crown', 'Crown'),
        ('root_canal', 'Root Canal'),
        ('implant', 'Implant'),
        ('bridge', 'Bridge'),
        ('missing', 'Missing'),
        ('watch', 'Watch'),
    ]

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='tooth_conditions')
    tooth_number = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(32)]
    )
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES)
    notes = EncryptedTextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    class Meta:
        ordering = ['tooth_number']
        constraints = [
            models.UniqueConstraint(fields=['patient', 'tooth_number'], name='unique_tooth_per_patient'),
        ]

    def __str__(self):
        return f"{self.patient} — #{self.tooth_number} {self.get_condition_display()}"
