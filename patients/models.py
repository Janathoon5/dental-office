from django.db import models
from django.contrib.auth.models import User
from encrypted_model_fields.fields import EncryptedCharField, EncryptedTextField
from dental_office.mixins import SoftDeleteModel
from .validators import validate_birth_date, validate_phone


RECALL_INTERVAL_CHOICES = [
    (3, 'Every 3 months'),
    (4, 'Every 4 months'),
    (6, 'Every 6 months'),
    (12, 'Every 12 months'),
]


class Patient(SoftDeleteModel):
    user = models.OneToOneField(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='patient_profile'
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField(validators=[validate_birth_date])
    phone = models.CharField(max_length=20, validators=[validate_phone])
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    insurance_provider = EncryptedCharField(max_length=100, blank=True)
    insurance_id = EncryptedCharField(max_length=100, blank=True)
    allergies = EncryptedTextField(blank=True)
    medical_notes = EncryptedTextField(blank=True)
    recall_interval_months = models.PositiveSmallIntegerField(
        'Cleaning recall interval', choices=RECALL_INTERVAL_CHOICES, default=6,
        help_text='How often this patient should come back for a cleaning/checkup.',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return f"{self.last_name}, {self.first_name}"

    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class MedicalAlert(models.Model):
    TYPE_CHOICES = [
        ('allergy', 'Allergy'),
        ('medication', 'Medication'),
        ('condition', 'Medical Condition'),
        ('other', 'Other'),
    ]
    SEVERITY_CHOICES = [
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    ]

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='medical_alerts')
    alert_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='allergy')
    description = models.CharField(max_length=300)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='high')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-severity', 'alert_type']

    def __str__(self):
        return f"{self.get_alert_type_display()}: {self.description}"
