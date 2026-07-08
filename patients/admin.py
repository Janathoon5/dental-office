from django.contrib import admin
from dental_office.mixins import SoftDeleteAdminMixin
from .models import Patient, MedicalAlert


@admin.register(Patient)
class PatientAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ['last_name', 'first_name', 'date_of_birth', 'phone', 'email', 'insurance_provider', 'is_active']
    search_fields = ['first_name', 'last_name', 'phone', 'email']


@admin.register(MedicalAlert)
class MedicalAlertAdmin(admin.ModelAdmin):
    list_display = ['patient', 'alert_type', 'severity', 'description']
    list_filter = ['alert_type', 'severity']
