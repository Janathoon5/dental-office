from django.contrib import admin
from dental_office.mixins import SoftDeleteAdminMixin
from .models import TreatmentRecord, TreatmentPlan, TreatmentPlanItem


@admin.register(TreatmentRecord)
class TreatmentRecordAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ['patient', 'procedure', 'date', 'dentist', 'tooth_number', 'is_active']
    list_filter = ['date']
    search_fields = ['patient__first_name', 'patient__last_name', 'procedure']


class TreatmentPlanItemInline(admin.TabularInline):
    model = TreatmentPlanItem
    extra = 1


@admin.register(TreatmentPlan)
class TreatmentPlanAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ['patient', 'title', 'status', 'created_date', 'is_active']
    list_filter = ['status']
    inlines = [TreatmentPlanItemInline]
