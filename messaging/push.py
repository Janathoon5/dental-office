import logging
import os
import sys

import firebase_admin
from django.conf import settings
from firebase_admin import credentials, exceptions as fb_exceptions, messaging as fcm_messaging

logger = logging.getLogger(__name__)

_firebase_app = None
_firebase_init_attempted = False


def _get_firebase_app():
    """Lazy, cached init — deliberately not done at Django startup (apps.py
    ready()), since that would run for every management command including
    tests and migrations, which don't have real Firebase credentials.
    Also refuses to init under `manage.py test` even if a real credentials
    file happens to be present (as it is in local dev): otherwise a future
    test combining a staff message with a registered device token would
    fire a real network call to Firebase's production API."""
    global _firebase_app, _firebase_init_attempted
    if _firebase_init_attempted:
        return _firebase_app

    _firebase_init_attempted = True
    if 'test' in sys.argv:
        logger.info('Running under manage.py test; push notifications disabled.')
        return None

    cred_path = getattr(settings, 'FIREBASE_SERVICE_ACCOUNT_PATH', None)
    if not cred_path or not os.path.exists(cred_path):
        logger.info('Firebase service account not configured; push notifications disabled.')
        return None

    cred = credentials.Certificate(cred_path)
    _firebase_app = firebase_admin.initialize_app(cred)
    return _firebase_app


def send_new_message_push(message):
    """Notifies a patient's registered devices that staff sent them a new
    message. Data-only payload with a hardcoded generic string — PHI (the
    actual message content) must never transit FCM, so the real message
    body is never interpolated here. The app fetches and displays the real
    message via an authenticated API call once opened."""
    app = _get_firebase_app()
    if app is None:
        return

    patient = message.conversation.patient
    tokens = list(patient.device_tokens.values_list('fcm_token', flat=True))
    if not tokens:
        return

    stale_tokens = []
    for token in tokens:
        try:
            fcm_messaging.send(
                fcm_messaging.Message(
                    data={
                        'type': 'new_message',
                        'title': 'New message',
                        'body': 'You have a new message from your dental office.',
                    },
                    token=token,
                ),
                app=app,
            )
        except fcm_messaging.UnregisteredError:
            stale_tokens.append(token)
        except fb_exceptions.FirebaseError:
            logger.exception('Failed to send push notification to a device token.')

    if stale_tokens:
        patient.device_tokens.filter(fcm_token__in=stale_tokens).delete()
