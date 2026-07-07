from dental_office.roles import is_dentist, is_receptionist, is_staff_member


def user_roles(request):
    if not request.user.is_authenticated:
        return {}
    admin = request.user.is_superuser
    dentist = admin or is_dentist(request.user)
    receptionist = is_receptionist(request.user)

    pending_count = 0
    if is_staff_member(request.user):
        try:
            from appointments.models import AppointmentRequest
            AppointmentRequest.objects.expire_stale()
            pending_count = AppointmentRequest.objects.filter(status='pending').count()
        except Exception:
            pass

    return {
        'user_is_dentist': dentist,
        'user_is_receptionist': receptionist,
        'user_is_admin': admin,
        'pending_requests_count': pending_count,
    }
