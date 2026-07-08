from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models.signals import pre_save
from django.dispatch import receiver


@receiver(pre_save, sender=User)
def enforce_case_insensitive_unique_username(sender, instance, **kwargs):
    duplicate = User.objects.filter(username__iexact=instance.username).exclude(pk=instance.pk).exists()
    if duplicate:
        raise ValidationError(f"A user with the username '{instance.username}' already exists.")
