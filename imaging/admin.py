from django.contrib import admin

from dental_office.mixins import SoftDeleteAdminMixin
from .models import DentalImage


@admin.register(DentalImage)
class DentalImageAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ['patient', 'image_type', 'captured_date', 'uploaded_by', 'is_active']
    list_filter = ['image_type', 'is_active']
