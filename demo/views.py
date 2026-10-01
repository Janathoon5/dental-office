import threading

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.db import close_old_connections
from django.http import Http404
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from dental_office.roles import get_post_login_redirect

from .data import DEMO_USERS, reset_demo_practice


@ratelimit(key='ip', rate='30/m', block=True)
@require_POST
def demo_login(request, role):
    """One-click login as a demo account. Only exists while DEMO_MODE is on."""
    if not settings.DEMO_MODE or role not in DEMO_USERS:
        raise Http404
    user = User.objects.filter(username=DEMO_USERS[role][0]).first()
    if user is None:
        messages.error(request, "The demo practice isn't loaded yet. Please try again later.")
        return redirect('login')
    logout(request)
    login(request, user, backend='dental_office.backends.CaseInsensitiveModelBackend')
    return redirect(get_post_login_redirect(user))


def _reset_in_thread():
    close_old_connections()
    try:
        reset_demo_practice()
    finally:
        close_old_connections()


@require_POST
def reset_demo(request):
    """Reload the demo practice now (site admins only). Runs in the
    background: on the live site it can outlast the request timeout."""
    if not settings.DEMO_MODE or not request.user.is_superuser:
        raise Http404
    if settings.ANALYZE_DENIALS_IN_BACKGROUND:  # same switch: tests run background work inline
        threading.Thread(target=_reset_in_thread, daemon=True).start()
        messages.success(request, 'Resetting the demo practice. Refresh in about a minute to see the fresh data.')
    else:
        reset_demo_practice()
        messages.success(request, 'The demo practice has been reset.')
    return redirect('dashboard')
