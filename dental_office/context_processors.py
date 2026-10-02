from django.conf import settings

from dental_office.roles import get_patient_profile, is_clinical_staff, is_dentist, is_patient, is_receptionist, is_staff_member


DEMO_ROLES = [
    ('dentist', 'Dentist', 'bi-person-badge', 'Charts, treatment plans, AI insurance appeals'),
    ('frontdesk', 'Front desk', 'bi-calendar-check', 'Schedule, billing, recalls, reminders'),
    ('hygienist', 'Hygienist', 'bi-stars', 'Cleanings and clinical notes'),
    ('patient', 'Patient', 'bi-phone', 'The patient portal'),
]


def demo_mode(request):
    if not settings.DEMO_MODE:
        return {'demo_mode': False}
    return {'demo_mode': True, 'demo_roles': DEMO_ROLES}


def user_roles(request):
    if not request.user.is_authenticated:
        return {}
    admin = request.user.is_superuser
    dentist = admin or is_dentist(request.user)
    receptionist = is_receptionist(request.user)
    clinical = admin or is_clinical_staff(request.user)

    pending_count = 0
    if is_staff_member(request.user):
        try:
            from appointments.models import AppointmentRequest
            AppointmentRequest.objects.expire_stale()
            pending_count = AppointmentRequest.objects.filter(status='pending').count()
        except Exception:
            pass

    unread_messages = 0
    if is_patient(request.user):
        profile = get_patient_profile(request.user)
        conversation = getattr(profile, 'conversation', None) if profile else None
        if conversation is not None:
            unread_messages = conversation.messages.filter(read_at__isnull=True).exclude(sender=request.user).count()

    return {
        'portal_unread_messages': unread_messages,
        'user_is_dentist': dentist,
        'user_is_receptionist': receptionist,
        'user_is_hygienist': clinical and not dentist,
        'user_is_clinical': clinical,
        'user_is_admin': admin,
        'pending_requests_count': pending_count,
    }
