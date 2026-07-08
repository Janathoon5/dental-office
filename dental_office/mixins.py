from django.conf import settings
from django.db import models
from django.utils import timezone


class ActiveManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


class SoftDeleteModel(models.Model):
    """Flags records inactive instead of removing them, so PHI stays
    available for compliance/audit purposes. `objects` (the default
    manager) only returns active rows; use `all_objects` to see everything,
    including soft-deleted rows."""

    is_active = models.BooleanField(default=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True
        # Django uses the *base* manager (not the default one) internally for
        # forward FK lookups (e.g. invoice.patient) and cascade collection.
        # Without this, any existing record pointing at a soft-deleted row
        # would raise DoesNotExist the moment someone accessed that relation.
        base_manager_name = 'all_objects'

    def delete(self, using=None, keep_parents=False, deleted_by=None):
        self.is_active = False
        self.deleted_at = timezone.now()
        self.deleted_by = deleted_by
        self.save(using=using, update_fields=['is_active', 'deleted_at', 'deleted_by'])


class SoftDeleteAdminMixin:
    """Pair with SoftDeleteModel: shows soft-deleted rows in the admin
    instead of hiding them, and makes both single-object and bulk delete
    actions go through the model's soft-delete override (Django's default
    bulk action calls queryset.delete(), which bypasses a model's delete()
    entirely)."""

    def get_queryset(self, request):
        return self.model.all_objects.all()

    def delete_model(self, request, obj):
        obj.delete(deleted_by=request.user)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            obj.delete(deleted_by=request.user)
