from django.contrib.auth.models import User
from django.db import models
from encrypted_model_fields.fields import EncryptedTextField
from dental_office.mixins import SoftDeleteModel
from patients.models import Patient


class Conversation(SoftDeleteModel):
    """One thread per patient — not full multi-party chat. Mirrors the
    existing convention that no per-staff patient-assignment ACL exists
    anywhere in this codebase: any staff member can post into any patient's
    conversation, same as any staff member can already view any patient's
    record."""

    patient = models.OneToOneField(Patient, on_delete=models.CASCADE, related_name='conversation')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(SoftDeleteModel.Meta):
        pass

    def __str__(self):
        return f"Conversation with {self.patient}"


class Message(SoftDeleteModel):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='sent_messages')
    body = EncryptedTextField()
    sent_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ['sent_at']

    def __str__(self):
        return f"Message in {self.conversation} at {self.sent_at}"


class DeviceToken(SoftDeleteModel):
    PLATFORM_CHOICES = [
        ('ios', 'iOS'),
        ('android', 'Android'),
    ]

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='device_tokens')
    fcm_token = models.CharField(max_length=255, unique=True)
    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(SoftDeleteModel.Meta):
        pass

    def __str__(self):
        return f"{self.platform} device for {self.patient}"
