import datetime

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from patients.models import Patient
from .models import PatientInvite


class PortalAccessGateTests(TestCase):
    """Regression guard for two gaps in patient_required: a Patient-group user
    with no linked Patient record 500'd on every portal page, and a
    soft-deleted patient kept full portal access — so 'deleting' a patient in
    the admin left their login working against their own records."""

    def setUp(self):
        self.group, _ = Group.objects.get_or_create(name='Patient')

    def _portal_user(self, username, with_patient=True, soft_deleted=False):
        user = User.objects.create_user(username=username, password='testpass123')
        user.groups.add(self.group)
        if with_patient:
            patient = Patient.objects.create(
                first_name='Portal', last_name=username,
                date_of_birth=datetime.date(1990, 1, 1), phone='555-0000', user=user,
            )
            if soft_deleted:
                patient.delete()
        return user

    def test_user_without_patient_record_is_redirected_not_500(self):
        self.client.force_login(self._portal_user('orphaned', with_patient=False))
        response = self.client.get(reverse('patient_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_soft_deleted_patient_loses_portal_access(self):
        self.client.force_login(self._portal_user('softdeleted', soft_deleted=True))
        for name in ('patient_dashboard', 'patient_invoices', 'patient_records'):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, f'{name} should be blocked')
            self.assertIn(reverse('login'), response.url)

    def test_active_patient_still_has_access(self):
        self.client.force_login(self._portal_user('healthy'))
        response = self.client.get(reverse('patient_dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_blocked_portal_user_does_not_land_in_a_redirect_loop(self):
        self.client.force_login(self._portal_user('looper', with_patient=False))
        response = self.client.get(reverse('patient_dashboard'), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.redirect_chain), 1)


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
