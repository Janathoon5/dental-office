"""Shared pieces for emails to patients: the office's name as the sender,
its contact details as a signature, and dates written out in full."""
from email.utils import formataddr, parseaddr

from django.conf import settings
from django.core.mail import send_mail


def _office():
    from billing.models import OfficeSettings  # billing imports appointments
    return OfficeSettings.load()


def long_date(day):
    """Friday, October 2, 2026"""
    return f'{day:%A}, {day:%B} {day.day}, {day.year}'


def short_time(time):
    """9:00 AM"""
    return time.strftime('%I:%M %p').lstrip('0')


def office_name():
    return _office().office_name or 'your dental office'


def contact_line():
    """How to reach the office, for "if you need to reschedule..." lines."""
    phone = _office().phone
    return f'please call us at {phone}' if phone else 'please contact the office'


def signature(patient=None):
    office = _office()
    lines = [office.office_name or 'Your dental office']
    lines += [line.strip() for line in office.address.splitlines() if line.strip()]
    if office.phone:
        lines.append(f'Phone: {office.phone}')
    if patient is not None and patient.user_id:
        lines.append(f'Patient portal: {settings.SITE_URL}/patient/')
    return '\n'.join(lines)


def from_address():
    """The site's sending address, shown under the office's name."""
    name, address = parseaddr(settings.DEFAULT_FROM_EMAIL)
    return formataddr((_office().office_name or name or 'Dental Office', address))


def send_patient_email(subject, body, to, patient=None):
    """Send body to one address, signed with the office's details."""
    send_mail(subject, f'{body}\n\n{signature(patient)}\n', from_address(), [to])
