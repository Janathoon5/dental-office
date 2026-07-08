from functools import wraps
from django.shortcuts import redirect


def is_patient(user):
    return user.groups.filter(name='Patient').exists()


def is_dentist(user):
    return hasattr(user, 'staff_profile') and user.staff_profile.role == 'dentist'


def is_receptionist(user):
    return hasattr(user, 'staff_profile') and user.staff_profile.role == 'receptionist'


def is_staff_member(user):
    return user.is_staff or hasattr(user, 'staff_profile')


def get_post_login_redirect(user):
    """Return the URL name a user should land on after login."""
    if user.is_superuser or user.is_staff:
        return 'dashboard'
    if is_patient(user):
        return 'patient_dashboard'
    if is_dentist(user) or is_receptionist(user):
        return 'dashboard'
    return 'dashboard'


def _require_2fa(user):
    """Staff accounts must have confirmed 2FA. Returns a redirect if not set
    up yet, or None if the user is clear to proceed."""
    from staff.models import TOTPDevice
    try:
        if not user.totp_device.confirmed:
            return redirect('setup_2fa')
    except TOTPDevice.DoesNotExist:
        return redirect('setup_2fa')
    return None


def patient_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not is_patient(request.user):
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


def staff_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not is_staff_member(request.user):
            return redirect('patient_dashboard')
        needs_2fa = _require_2fa(request.user)
        if needs_2fa:
            return needs_2fa
        return view_func(request, *args, **kwargs)
    return wrapper


def dentist_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not (request.user.is_superuser or is_dentist(request.user)):
            return redirect('dashboard')
        needs_2fa = _require_2fa(request.user)
        if needs_2fa:
            return needs_2fa
        return view_func(request, *args, **kwargs)
    return wrapper
