from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.db import models
from encrypted_model_fields.fields import EncryptedTextField

from dental_office.mixins import SoftDeleteModel
from patients.models import Patient


def dental_image_upload_path(instance, filename):
    ext = Path(filename).suffix.lower()
    return f'patients/{instance.patient_id}/{instance.image_type}/{uuid4().hex}{ext}'


class DentalImage(SoftDeleteModel):
    IMAGE_TYPE_CHOICES = [
        ('xray', 'X-Ray'),
        ('photo', 'Photo'),
    ]

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='dental_images')
    image_type = models.CharField(max_length=10, choices=IMAGE_TYPE_CHOICES)
    image = models.ImageField(upload_to=dental_image_upload_path)
    captured_date = models.DateField()
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='uploaded_dental_images',
    )
    uploaded_by_patient = models.BooleanField(default=False, editable=False)
    tooth_number = models.CharField(max_length=20, blank=True)
    caption = EncryptedTextField(blank=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ['image_type', '-captured_date']

    def __str__(self):
        return f"{self.patient} — {self.get_image_type_display()} ({self.captured_date})"
