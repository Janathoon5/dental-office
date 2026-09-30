from django.contrib import admin
from .models import Appointment, AppointmentRequest, ReminderLog, RecallNotice, ScheduledJobRun


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ['patient', 'dentist', 'date', 'start_time', 'appointment_type', 'status']
    list_filter = ['status', 'appointment_type', 'date']
    search_fields = ['patient__first_name', 'patient__last_name']
    date_hierarchy = 'date'


@admin.register(AppointmentRequest)
class AppointmentRequestAdmin(admin.ModelAdmin):
    list_display = ['first_name', 'last_name', 'phone', 'preferred_date', 'appointment_type', 'status', 'submitted_at']
    list_filter = ['status', 'appointment_type']


@admin.register(ReminderLog)
class ReminderLogAdmin(admin.ModelAdmin):
    list_display = ['appointment', 'status', 'recipient_email', 'days_before', 'sent_at']
    list_filter = ['status']


@admin.register(RecallNotice)
class RecallNoticeAdmin(admin.ModelAdmin):
    list_display = ['patient', 'due_date', 'sent_at', 'status', 'recipient_email']
    list_filter = ['status']


@admin.register(ScheduledJobRun)
class ScheduledJobRunAdmin(admin.ModelAdmin):
    list_display = ['ran_at', 'succeeded', 'summary']
    list_filter = ['succeeded']
