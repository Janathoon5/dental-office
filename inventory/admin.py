from django.contrib import admin
from .models import SupplyItem


@admin.register(SupplyItem)
class SupplyItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'quantity', 'unit', 'min_quantity', 'is_low_stock']
    list_filter = ['category']
    search_fields = ['name']
