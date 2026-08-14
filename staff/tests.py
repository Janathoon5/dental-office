import pyotp
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import TOTPDevice


class AdminLoginBypassTests(TestCase):
    """Regression guard: Django's built-in /admin/login/ used to authenticate
    independently of this app's login_view/verify_otp flow, letting a
    superuser skip 2FA entirely by navigating straight there."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='superadmin', password='TestPass123!', email='a@b.com'
        )
        TOTPDevice.objects.create(user=self.superuser, secret='JBSWY3DPEHPK3PXP', confirmed=True)

    def test_admin_login_page_redirects_to_app_login_instead_of_authenticating(self):
        response = self.client.get('/admin/login/?next=/admin/')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('login')))

    def test_posting_credentials_directly_to_admin_login_does_not_authenticate(self):
        self.client.post('/admin/login/', {
            'username': 'superadmin', 'password': 'TestPass123!', 'next': '/admin/',
        })
        # Django admin templates require a collectstatic manifest this dev
        # environment doesn't have, so assert on session auth state directly
        # rather than rendering a page.
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_legitimate_login_still_requires_otp_and_lands_back_on_admin(self):
        login_response = self.client.post(
            f"{reverse('login')}?next=/admin/",
            {'username': 'superadmin', 'password': 'TestPass123!', 'next': '/admin/'},
        )
        self.assertEqual(login_response.status_code, 302)
        self.assertEqual(login_response.url, reverse('verify_otp'))

        # Not authenticated yet — OTP step hasn't been completed.
        self.assertNotIn('_auth_user_id', self.client.session)

        otp = pyotp.TOTP('JBSWY3DPEHPK3PXP').now()
        otp_response = self.client.post(reverse('verify_otp'), {'otp': otp})
        self.assertEqual(otp_response.status_code, 302)
        self.assertEqual(otp_response.url, '/admin/')

        self.assertEqual(self.client.session['_auth_user_id'], str(self.superuser.pk))
