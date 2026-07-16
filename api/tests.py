import datetime

from django.contrib.auth.models import Group, User
from rest_framework.test import APITestCase
from rest_framework import status

from appointments.models import Appointment, AppointmentRequest
from billing.models import Invoice, Payment
from clinical.models import TreatmentPlan, TreatmentPlanItem, TreatmentRecord
from messaging.models import Conversation, DeviceToken, Message
from patient_portal.models import PatientInvite
from patients.models import Patient
from staff.models import StaffProfile
from auditlog.models import LogEntry


def _next_monday():
    """A future date guaranteed to fall within office hours (Monday
    8am-5pm per patient_portal/validators.py:OFFICE_HOURS)."""
    d = datetime.date.today()
    days_ahead = (0 - d.weekday()) % 7 or 7
    return d + datetime.timedelta(days=days_ahead)


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


class _PatientAPITestCase(APITestCase):
    """Base for the tests below — patient + auth headers, so each test
    class doesn't repeat the same login boilerplate as PatientAuthTests."""

    def setUp(self):
        self.patient_user = User.objects.create_user(username='patientuser', password='testpass123')
        patient_group, _ = Group.objects.get_or_create(name='Patient')
        self.patient_user.groups.add(patient_group)
        self.patient = Patient.objects.create(
            first_name='Api', last_name='Test',
            date_of_birth=datetime.date(1990, 1, 1), phone='555-0000',
            user=self.patient_user,
        )
        response = self.client.post('/api/v1/auth/login/', {
            'username': 'patientuser', 'password': 'testpass123',
        })
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")


class AppointmentTests(_PatientAPITestCase):
    def setUp(self):
        super().setUp()
        today = datetime.date.today()
        self.upcoming = Appointment.objects.create(
            patient=self.patient, date=today + datetime.timedelta(days=7),
            start_time=datetime.time(9, 0), status='scheduled',
        )
        self.past = Appointment.objects.create(
            patient=self.patient, date=today - datetime.timedelta(days=7),
            start_time=datetime.time(9, 0), status='completed',
        )

    def test_default_scope_returns_only_upcoming(self):
        response = self.client.get('/api/v1/appointments/')
        self.assertEqual(response.status_code, 200)
        ids = [a['id'] for a in response.data['results']]
        self.assertIn(self.upcoming.id, ids)
        self.assertNotIn(self.past.id, ids)

    def test_past_scope_returns_only_past(self):
        response = self.client.get('/api/v1/appointments/?scope=past')
        self.assertEqual(response.status_code, 200)
        ids = [a['id'] for a in response.data['results']]
        self.assertIn(self.past.id, ids)
        self.assertNotIn(self.upcoming.id, ids)


class AppointmentRequestTests(_PatientAPITestCase):
    def test_create_within_office_hours_succeeds(self):
        response = self.client.post('/api/v1/appointment-requests/', {
            'preferred_date': _next_monday().isoformat(),
            'preferred_time': '09:00:00',
            'appointment_type': 'checkup',
            'message': 'Test',
        })
        self.assertEqual(response.status_code, 201)
        appt_request = AppointmentRequest.objects.get(pk=response.data['id'])
        self.assertEqual(appt_request.patient, self.patient)
        self.assertEqual(appt_request.first_name, self.patient.first_name)

    def test_create_outside_office_hours_rejected(self):
        response = self.client.post('/api/v1/appointment-requests/', {
            'preferred_date': _next_monday().isoformat(),
            'preferred_time': '20:00:00',
            'appointment_type': 'checkup',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('preferred_time', response.data)

    def test_create_past_date_rejected(self):
        response = self.client.post('/api/v1/appointment-requests/', {
            'preferred_date': (datetime.date.today() - datetime.timedelta(days=1)).isoformat(),
            'preferred_time': '09:00:00',
            'appointment_type': 'checkup',
        })
        self.assertEqual(response.status_code, 400)

    def test_edit_pending_request(self):
        appt_request = AppointmentRequest.objects.create(
            patient=self.patient, first_name='Api', last_name='Test', phone='555-0000',
            preferred_date=_next_monday(), preferred_time=datetime.time(9, 0),
        )
        response = self.client.patch(f'/api/v1/appointment-requests/{appt_request.pk}/', {
            'preferred_time': '10:00:00',
        })
        self.assertEqual(response.status_code, 200)
        appt_request.refresh_from_db()
        self.assertEqual(appt_request.preferred_time, datetime.time(10, 0))

    def test_cancel_deletes_pending_request(self):
        appt_request = AppointmentRequest.objects.create(
            patient=self.patient, first_name='Api', last_name='Test', phone='555-0000',
            preferred_date=_next_monday(), preferred_time=datetime.time(9, 0),
        )
        response = self.client.delete(f'/api/v1/appointment-requests/{appt_request.pk}/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(AppointmentRequest.objects.filter(pk=appt_request.pk).exists())

    def test_approved_request_not_visible_or_editable(self):
        appt_request = AppointmentRequest.objects.create(
            patient=self.patient, first_name='Api', last_name='Test', phone='555-0000',
            preferred_date=_next_monday(), preferred_time=datetime.time(9, 0),
            status='approved',
        )
        list_response = self.client.get('/api/v1/appointment-requests/')
        ids = [r['id'] for r in list_response.data['results']]
        self.assertNotIn(appt_request.id, ids)

        detail_response = self.client.patch(f'/api/v1/appointment-requests/{appt_request.pk}/', {
            'preferred_time': '10:00:00',
        })
        self.assertEqual(detail_response.status_code, 404)


class RecordsTests(_PatientAPITestCase):
    def test_treatment_records_list(self):
        TreatmentRecord.objects.create(
            patient=self.patient, date=datetime.date.today(),
            procedure='Cleaning', notes='All good',
        )
        response = self.client.get('/api/v1/records/treatment-records/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['results'][0]['procedure'], 'Cleaning')
        self.assertEqual(response.data['results'][0]['notes'], 'All good')

    def test_treatment_plans_list_includes_items_and_total_cost(self):
        plan = TreatmentPlan.objects.create(patient=self.patient, title='Root canal plan')
        TreatmentPlanItem.objects.create(plan=plan, procedure='X-ray', estimated_cost=50)
        TreatmentPlanItem.objects.create(plan=plan, procedure='Root canal', estimated_cost=800)

        response = self.client.get('/api/v1/records/treatment-plans/')
        self.assertEqual(response.status_code, 200)
        data = response.data['results'][0]
        self.assertEqual(len(data['items']), 2)
        self.assertEqual(float(data['total_cost']), 850.0)

    def test_soft_deleted_record_not_returned(self):
        record = TreatmentRecord.objects.create(
            patient=self.patient, date=datetime.date.today(), procedure='Extraction',
        )
        record.delete()
        response = self.client.get('/api/v1/records/treatment-records/')
        self.assertEqual(response.data['results'], [])


class InvoiceTests(_PatientAPITestCase):
    def test_invoice_list_includes_computed_balance(self):
        invoice = Invoice.objects.create(patient=self.patient, subtotal=200, insurance_amount=50)
        Payment.objects.create(invoice=invoice, amount=50)

        response = self.client.get('/api/v1/invoices/')
        self.assertEqual(response.status_code, 200)
        data = response.data['results'][0]
        self.assertEqual(float(data['patient_owes']), 150.0)
        self.assertEqual(float(data['amount_paid']), 50.0)
        self.assertEqual(float(data['balance_due']), 100.0)


class AcceptInviteTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='invited@example.com', is_active=False)
        self.patient = Patient.objects.create(
            first_name='Invited', last_name='Patient',
            date_of_birth=datetime.date(1990, 1, 1), phone='555-1111',
            user=self.user,
        )
        self.invite = PatientInvite.objects.create(patient=self.patient)

    def test_valid_invite_activates_user_and_returns_tokens(self):
        response = self.client.post('/api/v1/auth/accept-invite/', {
            'token': str(self.invite.token), 'password': 'SecurePass123!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertTrue(self.user.check_password('SecurePass123!'))
        self.assertTrue(self.user.groups.filter(name='Patient').exists())

        self.invite.refresh_from_db()
        self.assertTrue(self.invite.used)

    def test_already_used_invite_rejected(self):
        self.invite.used = True
        self.invite.save()
        response = self.client.post('/api/v1/auth/accept-invite/', {
            'token': str(self.invite.token), 'password': 'SecurePass123!',
        })
        self.assertEqual(response.status_code, 400)

    def test_unknown_token_rejected(self):
        response = self.client.post('/api/v1/auth/accept-invite/', {
            'token': '00000000-0000-0000-0000-000000000000', 'password': 'SecurePass123!',
        })
        self.assertEqual(response.status_code, 400)

    def test_weak_password_rejected(self):
        response = self.client.post('/api/v1/auth/accept-invite/', {
            'token': str(self.invite.token), 'password': '123',
        })
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)


class MessageTests(_PatientAPITestCase):
    def test_list_messages_with_no_prior_conversation_returns_empty(self):
        response = self.client.get('/api/v1/messages/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['results'], [])
        self.assertTrue(Conversation.objects.filter(patient=self.patient).exists())

    def test_patient_can_send_message(self):
        response = self.client.post('/api/v1/messages/', {'body': 'Hello, I have a question.'})
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data['is_from_staff'])

        message = Message.objects.get(pk=response.data['id'])
        self.assertEqual(message.sender, self.patient_user)
        self.assertEqual(message.body, 'Hello, I have a question.')
        self.assertEqual(message.conversation.patient, self.patient)

    def test_staff_message_flagged_as_from_staff(self):
        staff_user = User.objects.create_user(username='staffuser2', password='testpass123')
        StaffProfile.objects.create(user=staff_user, role='dentist')
        conversation = Conversation.objects.create(patient=self.patient)
        Message.objects.create(conversation=conversation, sender=staff_user, body='We got your message.')

        response = self.client.get('/api/v1/messages/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['results'][0]['is_from_staff'])

    def test_mark_read_only_affects_staff_messages(self):
        staff_user = User.objects.create_user(username='staffuser3', password='testpass123')
        StaffProfile.objects.create(user=staff_user, role='dentist')
        conversation = Conversation.objects.create(patient=self.patient)
        staff_message = Message.objects.create(conversation=conversation, sender=staff_user, body='From staff')
        patient_message = Message.objects.create(conversation=conversation, sender=self.patient_user, body='From patient')

        response = self.client.post('/api/v1/messages/mark-read/')
        self.assertEqual(response.status_code, 204)

        staff_message.refresh_from_db()
        patient_message.refresh_from_db()
        self.assertIsNotNone(staff_message.read_at)
        self.assertIsNone(patient_message.read_at)

    def test_register_device_token(self):
        response = self.client.post('/api/v1/devices/register/', {
            'fcm_token': 'abc123', 'platform': 'android',
        })
        self.assertEqual(response.status_code, 201)
        token = DeviceToken.objects.get(fcm_token='abc123')
        self.assertEqual(token.patient, self.patient)
        self.assertEqual(token.platform, 'android')

    def test_re_registering_same_token_updates_rather_than_duplicates(self):
        self.client.post('/api/v1/devices/register/', {'fcm_token': 'abc123', 'platform': 'android'})
        response = self.client.post('/api/v1/devices/register/', {'fcm_token': 'abc123', 'platform': 'ios'})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(DeviceToken.objects.filter(fcm_token='abc123').count(), 1)
        self.assertEqual(DeviceToken.objects.get(fcm_token='abc123').platform, 'ios')
