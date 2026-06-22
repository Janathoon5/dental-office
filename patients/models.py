from django.db import models


class Patient(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    insurance_provider = models.CharField(max_length=100, blank=True)
    insurance_id = models.CharField(max_length=100, blank=True)
    allergies = models.TextField(blank=True)
    medical_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
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
