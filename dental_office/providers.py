"""Picking a dentist or hygienist in forms, labeled by name instead of login."""
from django import forms
from django.contrib.auth.models import User

CLINICAL_ROLES = ('dentist', 'hygienist')


def _role(user):
    return getattr(getattr(user, 'staff_profile', None), 'role', '')


def provider_name(user):
    """"Dr. Elena Park" for a dentist, "Marcus Reed" for anyone else."""
    name = user.get_full_name() or user.username
    return f'Dr. {name}' if _role(user) == 'dentist' else name


def provider_label(user):
    role = _role(user)
    if role == 'dentist':
        return f'{provider_name(user)} (Dentist)'
    if role == 'hygienist':
        return f'{provider_name(user)} (Hygienist)'
    return provider_name(user)


class ProviderChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return provider_label(obj)


def limit_to_providers(field, current=None):
    """Restrict a provider dropdown to clinical staff, keeping whoever is
    already saved on the record so editing an older record still validates."""
    queryset = User.objects.filter(staff_profile__role__in=CLINICAL_ROLES)
    if current is not None:
        queryset = queryset | User.objects.filter(pk=current.pk)
    field.queryset = queryset.select_related('staff_profile').distinct().order_by('first_name', 'last_name', 'username')
