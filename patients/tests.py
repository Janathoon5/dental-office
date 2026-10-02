import datetime

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from staff.models import StaffProfile, TOTPDevice
from patient_portal.models import PatientInvite
from .models import MedicalAlert, Patient


class PatientAccessControlTests(TestCase):
    """Regression guard for the cross-patient IDOR bug: these views must be
    staff-only, since patient portal accounts are also plain authenticated
    Users and must not be able to browse other patients' records."""

    def setUp(self):
        self.other_patient = Patient.objects.create(
            first_name='Other', last_name='Patient',
            date_of_birth=datetime.date(1990, 1, 1), phone='555-0000',
        )
        self.alert = MedicalAlert.objects.create(
            patient=self.other_patient, description='Penicillin allergy',
        )

        self.patient_user = User.objects.create_user(username='patientuser', password='testpass123')
        patient_group, _ = Group.objects.get_or_create(name='Patient')
        self.patient_user.groups.add(patient_group)
        self.own_patient = Patient.objects.create(
            first_name='Self', last_name='Patient',
            date_of_birth=datetime.date(1991, 2, 2), phone='555-1111',
            user=self.patient_user,
        )

        self.staff_user = User.objects.create_user(username='staffuser', password='testpass123')
        StaffProfile.objects.create(user=self.staff_user, role='dentist')
        TOTPDevice.objects.create(user=self.staff_user, secret='JBSWY3DPEHPK3PXP', confirmed=True)

    def _urls(self):
        return [
            reverse('patient_list'),
            reverse('patient_add'),
            reverse('patient_detail', args=[self.other_patient.pk]),
            reverse('patient_edit', args=[self.other_patient.pk]),
            reverse('send_patient_invite', args=[self.other_patient.pk]),
            reverse('alert_add', args=[self.other_patient.pk]),
            reverse('alert_delete', args=[self.alert.pk]),
            reverse('staff_send_message', args=[self.other_patient.pk]),
        ]

    def test_patient_account_is_blocked_from_every_staff_view(self):
        self.client.force_login(self.patient_user)
        for url in self._urls():
            response = self.client.get(url)
            self.assertEqual(
                response.status_code, 302,
                f'{url} should redirect a patient-role account, got {response.status_code}',
            )

    def test_staff_account_can_reach_get_views(self):
        self.client.force_login(self.staff_user)
        for url in (reverse('patient_list'), reverse('patient_add'),
                    reverse('patient_detail', args=[self.other_patient.pk]),
                    reverse('patient_edit', args=[self.other_patient.pk])):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, f'{url} should be reachable by staff')

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse('patient_detail', args=[self.other_patient.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)


class SendPatientInviteTests(TestCase):
    """Regression guard: re-sending a portal invite must invalidate any
    earlier unused invite for that patient, otherwise an old email/link
    could still be used to reset the account's password long after a newer
    invite was issued and used."""

    def setUp(self):
        self.patient = Patient.objects.create(
            first_name='Invite', last_name='Target',
            date_of_birth=datetime.date(1990, 1, 1), phone='555-0000',
            email='invite-target@example.com',
        )
        self.staff_user = User.objects.create_user(username='staffuser2', password='testpass123')
        StaffProfile.objects.create(user=self.staff_user, role='dentist')
        TOTPDevice.objects.create(user=self.staff_user, secret='JBSWY3DPEHPK3PXP', confirmed=True)
        self.client.force_login(self.staff_user)

    def test_resending_invite_invalidates_the_previous_one(self):
        self.client.post(reverse('send_patient_invite', args=[self.patient.pk]))
        first_invite = PatientInvite.objects.get(patient=self.patient)
        self.assertTrue(first_invite.is_valid())

        self.client.post(reverse('send_patient_invite', args=[self.patient.pk]))
        first_invite.refresh_from_db()
        second_invite = PatientInvite.objects.filter(patient=self.patient).exclude(pk=first_invite.pk).get()

        self.assertFalse(first_invite.is_valid())
        self.assertTrue(second_invite.is_valid())


class PatientFormCheckTests(TestCase):
    """From the live-site test: a future birth date, a phone number like
    "call me maybe" and an exact duplicate patient were all accepted."""

    def setUp(self):
        staff = User.objects.create_user(username='deskchecks', password='pw')
        StaffProfile.objects.create(user=staff, role='receptionist')
        TOTPDevice.objects.create(user=staff, secret='JBSWY3DPEHPK3PXP', confirmed=True)
        self.client.force_login(staff)

    def _add(self, **overrides):
        data = {'first_name': 'Maria', 'last_name': 'Lopez', 'date_of_birth': '1985-03-02',
                'phone': '(555) 123-4567', 'email': '', 'address': '', 'insurance_provider': '',
                'insurance_id': '', 'allergies': '', 'medical_notes': '', 'recall_interval_months': 6}
        data.update(overrides)
        return self.client.post(reverse('patient_add'), data)

    def test_future_birth_date_is_refused(self):
        response = self._add(date_of_birth='2099-01-01')
        self.assertContains(response, "can&#x27;t be in the future")
        self.assertContains(response, 'value="2099-01-01"')  # what was typed stays in the box
        self.assertFalse(Patient.objects.exists())

    def test_phone_must_look_like_a_phone_number(self):
        response = self._add(phone='call me maybe')
        self.assertContains(response, 'Enter a phone number')
        for ok in ('(555) 123-4567', '555.123.4567', '+1 555 123 4567', '555-123-4567 x22'):
            Patient.objects.all().delete()
            self.assertEqual(self._add(phone=ok).status_code, 302, ok)

    def test_duplicate_patient_warns_then_saves_when_confirmed(self):
        existing = Patient.objects.create(first_name='Maria', last_name='Lopez', phone='555-0000',
                                          date_of_birth=datetime.date(1985, 3, 2))
        response = self._add(first_name='maria', last_name='LOPEZ')
        self.assertContains(response, 'is already a patient')
        self.assertContains(response, reverse('patient_detail', args=[existing.pk]))
        self.assertEqual(Patient.objects.count(), 1)
        self.assertEqual(self._add(confirm_duplicate='on').status_code, 302)
        self.assertEqual(Patient.objects.count(), 2)

    def test_editing_a_patient_is_not_flagged_as_their_own_duplicate(self):
        patient = Patient.objects.create(first_name='Maria', last_name='Lopez', phone='555-0000',
                                         date_of_birth=datetime.date(1985, 3, 2))
        response = self.client.post(reverse('patient_edit', args=[patient.pk]), {
            'first_name': 'Maria', 'last_name': 'Lopez', 'date_of_birth': '1985-03-02', 'phone': '555-0001',
            'recall_interval_months': 6})
        self.assertEqual(response.status_code, 302)
