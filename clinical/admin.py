from django.contrib import admin
from .models import TreatmentRecord, TreatmentPlan, TreatmentPlanItem


@admin.register(TreatmentRecord)
class TreatmentRecordAdmin(admin.ModelAdmin):
    list_display = ['patient', 'procedure', 'date', 'dentist', 'tooth_number']
    list_filter = ['date']
    search_fields = ['patient__first_name', 'patient__last_name', 'procedure']


class TreatmentPlanItemInline(admin.TabularInline):
    model = TreatmentPlanItem
    extra = 1


@admin.register(TreatmentPlan)
class TreatmentPlanAdmin(admin.ModelAdmin):
    list_display = ['patient', 'title', 'status', 'created_date']
    list_filter = ['status']
    inlines = [TreatmentPlanItemInline]
