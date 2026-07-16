from django.apps import AppConfig


class MessagingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'messaging'

    def ready(self):
        from auditlog.registry import auditlog
        from .models import Message
        auditlog.register(Message)
        from . import signals  # noqa: F401
