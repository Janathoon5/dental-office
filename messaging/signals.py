from django.db.models.signals import post_save
from django.dispatch import receiver

from dental_office.roles import is_patient

from .models import Message
from .push import send_new_message_push


@receiver(post_save, sender=Message)
def notify_patient_of_staff_message(sender, instance, created, **kwargs):
    """Only staff-authored messages trigger a push — a patient doesn't need
    a push notification for their own message."""
    if not created:
        return
    if instance.sender and not is_patient(instance.sender):
        send_new_message_push(instance)
