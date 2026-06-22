from django.contrib import admin
from .models import Invoice, Payment


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['pk', 'patient', 'date_issued', 'subtotal', 'insurance_amount', 'status']
    list_filter = ['status']
    search_fields = ['patient__first_name', 'patient__last_name']
    inlines = [PaymentInline]
