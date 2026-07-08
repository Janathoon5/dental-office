from django.apps import AppConfig


class PatientsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'patients'

    def ready(self):
        from auditlog.registry import auditlog
        from .models import Patient, MedicalAlert
        auditlog.register(Patient)
        auditlog.register(MedicalAlert)
