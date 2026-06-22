from django.db import models
from django.contrib.auth.models import User


class StaffProfile(models.Model):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('dentist', 'Dentist'),
        ('hygienist', 'Hygienist'),
        ('receptionist', 'Receptionist'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='staff_profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='receptionist')
    phone = models.CharField(max_length=20, blank=True)
    license_number = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.get_role_display()})"

    def is_clinical(self):
        return self.role in ('dentist', 'hygienist')


class TOTPDevice(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='totp_device')
    secret = models.CharField(max_length=64)
    confirmed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        status = 'active' if self.confirmed else 'unconfirmed'
        return f"2FA device for {self.user.username} ({status})"
