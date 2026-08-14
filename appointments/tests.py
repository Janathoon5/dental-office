import datetime

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse

from patients.models import Patient
from staff.models import StaffProfile, TOTPDevice
from .forms import AppointmentForm
from .models import Appointment, AppointmentRequest


class AppointmentAccessControlTests(TestCase):
    """Regression guard for the cross-patient IDOR bug: these views must be
    staff-only, since patient portal accounts are also plain authenticated
    Users and must not be able to browse other patients' appointments."""

    def setUp(self):
        self.other_patient = Patient.objects.create(
            first_name='Other', last_name='Patient',
            date_of_birth=datetime.date(1990, 1, 1), phone='555-0000',
        )
        self.appointment = Appointment.objects.create(
            patient=self.other_patient, date=timezone_today_plus(1),
            start_time=datetime.time(10, 0),
        )
        self.appt_request = AppointmentRequest.objects.create(
            first_name='Jane', last_name='Doe', phone='555-2222',
            preferred_date=timezone_today_plus(2), preferred_time=datetime.time(9, 0),
        )

        self.patient_user = User.objects.create_user(username='patientuser', password='testpass123')
        patient_group, _ = Group.objects.get_or_create(name='Patient')
        self.patient_user.groups.add(patient_group)

        self.staff_user = User.objects.create_user(username='staffuser', password='testpass123')
        StaffProfile.objects.create(user=self.staff_user, role='dentist')
        TOTPDevice.objects.create(user=self.staff_user, secret='JBSWY3DPEHPK3PXP', confirmed=True)

    def _get_urls(self):
        return [
            reverse('appointment_list'),
            reverse('appointment_detail', args=[self.appointment.pk]),
            reverse('appointment_add'),
            reverse('appointment_edit', args=[self.appointment.pk]),
            reverse('appointment_cancel', args=[self.appointment.pk]),
            reverse('request_list'),
            reverse('request_update', args=[self.appt_request.pk]),
            reverse('reminders_dashboard'),
            reverse('send_reminders_now'),
        ]

    def test_patient_account_is_blocked_from_every_staff_view(self):
        self.client.force_login(self.patient_user)
        for url in self._get_urls():
            response = self.client.get(url)
            self.assertEqual(
                response.status_code, 302,
                f'{url} should redirect a patient-role account, got {response.status_code}',
            )

    def test_staff_account_can_reach_get_views(self):
        self.client.force_login(self.staff_user)
        for url in (reverse('appointment_list'), reverse('appointment_detail', args=[self.appointment.pk]),
                    reverse('appointment_add'), reverse('appointment_edit', args=[self.appointment.pk]),
                    reverse('request_list'), reverse('reminders_dashboard')):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, f'{url} should be reachable by staff')

    def test_public_appointment_request_form_still_unauthenticated(self):
        response = self.client.get(reverse('appointment_request'))
        self.assertEqual(response.status_code, 200)


def timezone_today_plus(days):
    from django.utils import timezone
    return timezone.localdate() + datetime.timedelta(days=days)


class AppointmentDoubleBookingTests(TestCase):
    """Regression guard: a dentist must not be bookable for two overlapping
    appointments — previously AppointmentForm had no overlap check at all."""

    def setUp(self):
        self.patient = Patient.objects.create(
            first_name='One', last_name='Patient',
            date_of_birth=datetime.date(1990, 1, 1), phone='555-0000',
        )
        self.other_patient = Patient.objects.create(
            first_name='Two', last_name='Patient',
            date_of_birth=datetime.date(1990, 1, 1), phone='555-0001',
        )
        self.dentist_user = User.objects.create_user(username='drtooth', password='testpass123')
        StaffProfile.objects.create(user=self.dentist_user, role='dentist')
        self.date = timezone_today_plus(3)
        Appointment.objects.create(
            patient=self.patient, dentist=self.dentist_user,
            date=self.date, start_time=datetime.time(10, 0), duration_minutes=60,
        )

    def _form_data(self, **overrides):
        data = {
            'patient': self.other_patient.pk,
            'dentist': self.dentist_user.pk,
            'date': self.date.isoformat(),
            'start_time': '10:30',
            'duration_minutes': 30,
            'appointment_type': 'checkup',
            'status': 'scheduled',
            'notes': '',
        }
        data.update(overrides)
        return data

    def test_overlapping_appointment_for_same_dentist_is_rejected(self):
        form = AppointmentForm(data=self._form_data())
        self.assertFalse(form.is_valid())

    def test_non_overlapping_appointment_for_same_dentist_is_accepted(self):
        form = AppointmentForm(data=self._form_data(start_time='11:00'))
        self.assertTrue(form.is_valid(), form.errors)


class AppointmentRequestRateLimitTests(TestCase):
    """Regression guard: the public, unauthenticated appointment-request form
    had no throttling and could be hammered to flood the AppointmentRequest
    table or trigger a wave of confirmation emails.

    RATELIMIT_ENABLE is normally forced off under `manage.py test` (see
    settings.py) so unrelated tests aren't rate-limited by shared IP; this
    test explicitly re-enables it to verify the limit itself works."""

    @override_settings(RATELIMIT_ENABLE=True)
    def test_excessive_requests_from_one_ip_are_blocked(self):
        url = reverse('appointment_request')
        statuses = [self.client.get(url).status_code for _ in range(11)]
        self.assertIn(200, statuses[:10])
        self.assertEqual(statuses[-1], 403)
