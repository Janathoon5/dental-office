import datetime

from django.contrib.auth.models import Group, User
from rest_framework.test import APITestCase
from rest_framework import status

from patients.models import Patient
from staff.models import StaffProfile
from auditlog.models import LogEntry


class PatientAuthTests(APITestCase):
    def setUp(self):
        self.patient_user = User.objects.create_user(username='patientuser', password='testpass123')
        patient_group, _ = Group.objects.get_or_create(name='Patient')
        self.patient_user.groups.add(patient_group)
        self.patient = Patient.objects.create(
            first_name='Api', last_name='Test',
            date_of_birth=datetime.date(1990, 1, 1), phone='555-0000',
            user=self.patient_user,
        )

        self.staff_user = User.objects.create_user(username='staffuser', password='testpass123')
        StaffProfile.objects.create(user=self.staff_user, role='dentist')

    def test_patient_login_succeeds(self):
        response = self.client.post('/api/v1/auth/login/', {
            'username': 'patientuser', 'password': 'testpass123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_staff_login_rejected(self):
        response = self.client.post('/api/v1/auth/login/', {
            'username': 'staffuser', 'password': 'testpass123',
        })
        self.assertEqual(response.status_code, 400)

    def test_wrong_password_rejected(self):
        response = self.client.post('/api/v1/auth/login/', {
            'username': 'patientuser', 'password': 'wrongpass',
        })
        self.assertEqual(response.status_code, 401)

    def _login(self):
        response = self.client.post('/api/v1/auth/login/', {
            'username': 'patientuser', 'password': 'testpass123',
        })
        return response.data['access']

    def test_dashboard_requires_auth(self):
        response = self.client.get('/api/v1/dashboard/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_dashboard_with_valid_token(self):
        access = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        response = self.client.get('/api/v1/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['first_name'], 'Api')

    def test_profile_patch_updates_whitelisted_fields_only(self):
        access = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        response = self.client.patch('/api/v1/profile/', {
            'phone': '555-9999',
            'insurance_provider': 'Should Not Be Settable',
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('insurance_provider', response.data)
        self.patient.refresh_from_db()
        self.assertEqual(self.patient.phone, '555-9999')
        self.assertNotEqual(self.patient.insurance_provider, 'Should Not Be Settable')

    def test_profile_patch_is_audit_logged_with_correct_actor(self):
        LogEntry.objects.all().delete()
        access = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        self.client.patch('/api/v1/profile/', {'phone': '555-8888'})

        entries = LogEntry.objects.filter(object_pk=str(self.patient.pk))
        self.assertTrue(entries.exists())
        self.assertEqual(entries.first().actor, self.patient_user)
