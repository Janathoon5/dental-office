"""Template filters used across the site. Registered as a template builtin in
settings.TEMPLATES, so templates don't need {% load %}."""
from decimal import Decimal, InvalidOperation

from django import template

from dental_office.providers import provider_name as _provider_name

register = template.Library()


@register.filter
def money(value):
    """Dollar amount with thousands separators: 4405 -> "$4,405.00",
    -9953 -> "-$9,953.00"."""
    if value is None or value == '':
        return ''
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return value
    sign = '-' if amount < 0 else ''
    return f'{sign}${abs(amount):,.2f}'


@register.filter
def provider_name(user):
    """"Dr. Elena Park" for a dentist, plain name for anyone else."""
    return _provider_name(user) if user else ''
