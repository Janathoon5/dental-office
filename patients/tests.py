import datetime

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from staff.models import StaffProfile
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

    def _urls(self):
        return [
            reverse('patient_list'),
            reverse('patient_add'),
            reverse('patient_detail', args=[self.other_patient.pk]),
            reverse('patient_edit', args=[self.other_patient.pk]),
            reverse('send_patient_invite', args=[self.other_patient.pk]),
            reverse('alert_add', args=[self.other_patient.pk]),
            reverse('alert_delete', args=[self.alert.pk]),
        ]

    def test_patient_account_is_blocked_from_every_staff_view(self):
        self.client.login(username='patientuser', password='testpass123')
        for url in self._urls():
            response = self.client.get(url)
            self.assertEqual(
                response.status_code, 302,
                f'{url} should redirect a patient-role account, got {response.status_code}',
            )

    def test_staff_account_can_reach_get_views(self):
        self.client.login(username='staffuser', password='testpass123')
        for url in (reverse('patient_list'), reverse('patient_add'),
                    reverse('patient_detail', args=[self.other_patient.pk]),
                    reverse('patient_edit', args=[self.other_patient.pk])):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, f'{url} should be reachable by staff')

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse('patient_detail', args=[self.other_patient.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)
