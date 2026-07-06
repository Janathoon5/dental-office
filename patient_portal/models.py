import uuid
from django.db import models
from django.utils import timezone

INVITE_EXPIRY_DAYS = 7


class PatientInvite(models.Model):
    patient = models.ForeignKey(
        'patients.Patient', on_delete=models.CASCADE, related_name='invites'
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def is_valid(self):
        if self.used:
            return False
        expiry = self.created_at + timezone.timedelta(days=INVITE_EXPIRY_DAYS)
        return timezone.now() < expiry

    def __str__(self):
        return f"Invite for {self.patient} — {'used' if self.used else 'pending'}"
