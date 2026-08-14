from functools import wraps
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect


def is_patient(user):
    return user.groups.filter(name='Patient').exists()


def get_patient_profile(user):
    """The usable Patient record behind a portal login, or None.

    Group membership alone isn't enough to serve the portal: a user can be in
    the Patient group with no linked Patient at all (the link was cleared, or
    they were added to the group by hand), and every portal view dereferences
    `user.patient_profile` immediately — a 500 on page one. A soft-deleted
    patient also still resolves through that accessor, so 'deleting' a patient
    would otherwise leave their portal login working with full access to their
    records. Both cases have to be caught here, at the gate.
    """
    # RelatedObjectDoesNotExist subclasses AttributeError, so getattr's
    # default handles the missing-link case.
    profile = getattr(user, 'patient_profile', None)
    if profile is None or not profile.is_active:
        return None
    return profile


def is_dentist(user):
    return hasattr(user, 'staff_profile') and user.staff_profile.role == 'dentist'


def is_receptionist(user):
    return hasattr(user, 'staff_profile') and user.staff_profile.role == 'receptionist'


def is_clinical_staff(user):
    return hasattr(user, 'staff_profile') and user.staff_profile.is_clinical()


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
        if get_patient_profile(request.user) is None:
            # Log out rather than just redirecting to login: login_view sends
            # an already-authenticated patient straight back to the portal
            # dashboard, so a bare redirect would bounce forever.
            logout(request)
            messages.error(
                request,
                'This portal account is no longer active. Please contact the office.'
            )
            return redirect('login')
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


def clinical_required(view_func):
    """Dentists and hygienists — for logging treatment actually performed,
    as opposed to dentist_required's diagnosis/planning gate."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not (request.user.is_superuser or is_clinical_staff(request.user)):
            return redirect('dashboard')
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
