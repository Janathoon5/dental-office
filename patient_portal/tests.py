import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from patients.models import Patient
from .models import PatientInvite


class AcceptInviteTests(TestCase):
    """Regression guard for a bug where accept_invite crashed with an
    unhandled ValueError on every successful submission, because auth_login()
    was called without a backend while multiple AUTHENTICATION_BACKENDS are
    configured — the password was saved and the invite burned before the
    500, so patients could only recover by discovering the login page
    existed on their own."""

    def setUp(self):
        self.user = User.objects.create_user(username='inviteuser', is_active=False)
        self.patient = Patient.objects.create(
            first_name='Invite', last_name='Test',
            date_of_birth=datetime.date(1990, 1, 1), phone='555-0000',
            user=self.user,
        )
        self.invite = PatientInvite.objects.create(patient=self.patient)

    def test_accepting_invite_logs_the_patient_in_without_crashing(self):
        response = self.client.post(
            reverse('accept_invite', args=[str(self.invite.token)]),
            {'new_password1': 'S0meLongPassword!', 'new_password2': 'S0meLongPassword!'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('patient_dashboard'))

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.invite.refresh_from_db()
        self.assertTrue(self.invite.used)

        dashboard = self.client.get(reverse('patient_dashboard'))
        self.assertEqual(dashboard.status_code, 200)
