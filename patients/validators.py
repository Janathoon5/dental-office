import datetime
import re

from django.core.exceptions import ValidationError
from django.utils import timezone

_PHONE_CHARS = re.compile(r'^[\d\s().+\-]+((x|ext\.?)\s*\d{1,6})?$', re.IGNORECASE)


def validate_phone(value):
    """A phone number: 7 to 15 digits, written any common way, e.g.
    (555) 123-4567, 555.123.4567, +1 555 123 4567 or 555-123-4567 x22."""
    value = (value or '').strip()
    main = re.split(r'(?i)x|ext', value)[0]
    digits = re.sub(r'\D', '', main)
    if not _PHONE_CHARS.match(value) or not 7 <= len(digits) <= 15:
        raise ValidationError('Enter a phone number, for example (555) 123-4567.')


def validate_birth_date(value):
    if value and value > timezone.localdate():
        raise ValidationError("Date of birth can't be in the future.")
    if value and value < datetime.date(1900, 1, 1):
        raise ValidationError('Check the year: date of birth is before 1900.')
