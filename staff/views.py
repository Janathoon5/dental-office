import io
import base64
import pyotp
import qrcode
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.http import url_has_allowed_host_and_scheme
from .models import TOTPDevice
from dental_office.roles import get_post_login_redirect, is_staff_member


def _safe_next(request, next_url):
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return next_url
    return None


def login_view(request):
    if request.user.is_authenticated:
        return redirect(get_post_login_redirect(request.user))

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        next_url = _safe_next(request, request.POST.get('next'))
        user = authenticate(request, username=username, password=password)

        if user is None:
            messages.error(request, 'Invalid username or password.')
            return render(request, 'registration/login.html', {'next': next_url or ''})

        # Check if user has confirmed 2FA
        try:
            device = user.totp_device
            if device.confirmed:
                # Stash user id (and where to land afterward) in session and send to OTP step
                request.session['pending_2fa_user'] = user.pk
                request.session['pending_2fa_next'] = next_url
                return redirect('verify_otp')
        except TOTPDevice.DoesNotExist:
            pass

        # No 2FA set up — log in directly
        login(request, user)
        return redirect(next_url or get_post_login_redirect(user))

    next_url = _safe_next(request, request.GET.get('next'))
    return render(request, 'registration/login.html', {'next': next_url or ''})


OTP_ATTEMPT_LIMIT = 5


def verify_otp(request):
    user_id = request.session.get('pending_2fa_user')
    if not user_id:
        return redirect('login')

    if request.method == 'POST':
        from django.contrib.auth.models import User
        try:
            user = User.objects.get(pk=user_id)
            device = user.totp_device
        except Exception:
            del request.session['pending_2fa_user']
            return redirect('login')

        otp = request.POST.get('otp', '').strip().replace(' ', '')
        totp = pyotp.TOTP(device.secret)
        if totp.verify(otp, valid_window=1):
            del request.session['pending_2fa_user']
            next_url = request.session.pop('pending_2fa_next', None)
            request.session.pop('otp_attempts', None)
            user.backend = 'dental_office.backends.CaseInsensitiveModelBackend'
            login(request, user)
            return redirect(next_url or get_post_login_redirect(user))
        else:
            attempts = request.session.get('otp_attempts', 0) + 1
            request.session['otp_attempts'] = attempts
            if attempts >= OTP_ATTEMPT_LIMIT:
                del request.session['pending_2fa_user']
                request.session.pop('otp_attempts', None)
                messages.error(request, 'Too many incorrect codes. Please log in again.')
                return redirect('login')
            messages.error(request, 'Invalid code. Please try again.')

    return render(request, 'registration/verify_otp.html')


@login_required
def setup_2fa(request):
    user = request.user
    device, created = TOTPDevice.objects.get_or_create(
        user=user,
        defaults={'secret': pyotp.random_base32()}
    )
    if not created and device.confirmed:
        # Already set up — show management page
        return render(request, 'registration/2fa_manage.html', {'device': device})

    if not created and not device.confirmed:
        # Pending setup from before — reuse existing secret
        pass

    totp = pyotp.TOTP(device.secret)
    provisioning_uri = totp.provisioning_uri(
        name=user.username,
        issuer_name='Dental Office'
    )

    # Generate QR code as base64 image
    img = qrcode.make(provisioning_uri)
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    qr_b64 = base64.b64encode(buffer.getvalue()).decode()

    if request.method == 'POST':
        otp = request.POST.get('otp', '').strip().replace(' ', '')
        if totp.verify(otp, valid_window=1):
            device.confirmed = True
            device.save()
            messages.success(request, '2FA has been enabled on your account.')
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid code — please scan the QR code again and try.')

    return render(request, 'registration/setup_2fa.html', {
        'qr_b64': qr_b64,
        'secret': device.secret,
    })


@login_required
def disable_2fa(request):
    if is_staff_member(request.user):
        messages.error(request, '2FA is required for staff accounts and cannot be disabled.')
        return redirect('dashboard')
    if request.method == 'POST':
        try:
            request.user.totp_device.delete()
            messages.success(request, '2FA has been disabled.')
        except TOTPDevice.DoesNotExist:
            pass
        return redirect('dashboard')
    return render(request, 'registration/disable_2fa.html')
