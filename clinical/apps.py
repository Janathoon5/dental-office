from django.apps import AppConfig


class ClinicalConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'clinical'

    def ready(self):
        from auditlog.registry import auditlog
        from .models import TreatmentRecord, TreatmentPlan, TreatmentPlanItem
        auditlog.register(TreatmentRecord)
        auditlog.register(TreatmentPlan)
        auditlog.register(TreatmentPlanItem)
