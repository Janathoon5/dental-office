"""Visitor addresses and the pages shown when login lockout (django-axes) or
rate limiting (django-ratelimit) stops someone."""
import ipaddress

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render


def client_ip(request):
    """The visitor's IP address, for login lockout and rate limits.

    On Railway every request arrives through a proxy, so REMOTE_ADDR is the
    proxy's internal address, and it changes from request to request. The
    proxy adds the real visitor address to the end of X-Forwarded-For.
    Anything before that could have been typed by the visitor, so read the
    header from the right and take the first public address."""
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    for part in reversed(forwarded.split(',')):
        try:
            address = ipaddress.ip_address(part.strip())
        except ValueError:
            continue
        if address.is_global:
            return str(address)
    return request.META.get('REMOTE_ADDR', '')


def _wants_json(request):
    return request.path.startswith('/api/')


def lockout_response(request, original_response=None, credentials=None):
    """Shown by django-axes after AXES_FAILURE_LIMIT wrong passwords."""
    hours = settings.AXES_COOLOFF_TIME
    wait = 'an hour' if hours == 1 else f'{hours} hours'
    message = (f'Too many incorrect sign-in attempts. For your security, this account is locked '
               f'for {wait}. Try again later, or ask the office administrator to unlock it.')
    if _wants_json(request):
        return JsonResponse({'detail': message}, status=429)
    return render(request, 'registration/login.html', {'lockout_message': message, 'next': ''}, status=429)


def ratelimited(request, exception):
    """Shown by django-ratelimit when one visitor sends too many requests."""
    message = 'Too many requests in a short time. Please wait a minute and try again.'
    if _wants_json(request):
        return JsonResponse({'detail': message}, status=429)
    return render(request, 'errors/429.html', {'message': message}, status=429)
