from django.contrib import admin
from .models import StaffProfile


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'phone', 'license_number']
    list_filter = ['role']
