from django.contrib import admin
from dental_office.mixins import SoftDeleteAdminMixin
from .models import Invoice, Payment


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    # Payment is a SoftDeleteModel; without this, is_active/deleted_at/
    # deleted_by render as plain editable fields in the inline row, and
    # unchecking "is active" would soft-delete without going through
    # delete() (see SoftDeleteAdminMixin for the full rationale).
    readonly_fields = ['is_active', 'deleted_at', 'deleted_by']


@admin.register(Invoice)
class InvoiceAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ['pk', 'patient', 'date_issued', 'subtotal', 'insurance_amount', 'status', 'is_active']
    list_filter = ['status']
    search_fields = ['patient__first_name', 'patient__last_name']
    inlines = [PaymentInline]
