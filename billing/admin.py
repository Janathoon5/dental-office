from django.contrib import admin
from dental_office.mixins import SoftDeleteAdminMixin
from .models import ClaimDenial, Invoice, Payment, OfficeSettings


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    # Payment is a SoftDeleteModel; without this, is_active/deleted_at/
    # deleted_by render as plain editable fields in the inline row, and
    # unchecking "is active" would soft-delete without going through
    # delete() (see SoftDeleteAdminMixin for the full rationale).
    readonly_fields = ['is_active', 'deleted_at', 'deleted_by', 'void_reason']


@admin.register(Invoice)
class InvoiceAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ['pk', 'patient', 'date_issued', 'subtotal', 'insurance_amount', 'status', 'is_active']
    list_filter = ['status']
    search_fields = ['patient__first_name', 'patient__last_name']
    inlines = [PaymentInline]


@admin.register(OfficeSettings)
class OfficeSettingsAdmin(admin.ModelAdmin):
    """Single-row letterhead settings: can't add a second row or delete it."""

    def has_add_permission(self, request):
        return not OfficeSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ClaimDenial)
class ClaimDenialAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ['pk', 'invoice', 'insurer_name', 'status', 'appeal_deadline', 'ai_status', 'created_at', 'is_active']
    list_filter = ['status', 'ai_status']
    search_fields = ['invoice__patient__first_name', 'invoice__patient__last_name', 'claim_number']
