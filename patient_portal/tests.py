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


class PortalMessagesTests(TestCase):
    """From the live-site test: the office's replies only reached patients
    who used the mobile app; the website had no messages page."""

    def setUp(self):
        from messaging.models import Conversation, Message
        from staff.models import StaffProfile
        self.user = User.objects.create_user(username='msgpatient', password='pw')
        self.user.groups.add(Group.objects.get_or_create(name='Patient')[0])
        self.patient = Patient.objects.create(first_name='Maria', last_name='Lopez', phone='555-0000',
                                              date_of_birth=datetime.date(1985, 3, 2), user=self.user)
        self.desk = User.objects.create_user(username='msgdesk', password='pw', first_name='Sofia', last_name='Alvarez')
        StaffProfile.objects.create(user=self.desk, role='receptionist')
        self.conversation = Conversation.get_or_start_for(self.patient)
        self.staff_message = Message.objects.create(conversation=self.conversation, sender=self.desk,
                                                    body="We're appealing it with your X-ray.")
        self.client.force_login(self.user)

    def test_patient_sees_unread_office_messages(self):
        dashboard = self.client.get(reverse('patient_dashboard'))
        self.assertContains(dashboard, 'You have 1 new message from the office')
        page = self.client.get(reverse('patient_messages'))
        self.assertContains(page, "We&#x27;re appealing it with your X-ray.")
        self.assertContains(page, 'Sofia Alvarez')
        self.staff_message.refresh_from_db()
        self.assertIsNotNone(self.staff_message.read_at)
        self.assertNotContains(self.client.get(reverse('patient_dashboard')), 'new message')

    def test_patient_can_reply(self):
        response = self.client.post(reverse('patient_messages'), {'body': 'Thank you!'}, follow=True)
        self.assertContains(response, 'Message sent')
        reply = self.conversation.messages.order_by('-sent_at').first()
        self.assertEqual((reply.body, reply.sender), ('Thank you!', self.user))

    def test_empty_message_is_not_sent(self):
        self.client.post(reverse('patient_messages'), {'body': '   '})
        self.assertEqual(self.conversation.messages.count(), 1)

    def test_hygienist_is_not_called_doctor(self):
        from appointments.models import Appointment
        from django.utils import timezone
        from staff.models import StaffProfile
        hygienist = User.objects.create_user(username='msghyg', password='pw', first_name='Marcus', last_name='Reed')
        StaffProfile.objects.create(user=hygienist, role='hygienist')
        Appointment.objects.create(patient=self.patient, dentist=hygienist, start_time=datetime.time(9, 0),
                                   date=timezone.localdate() + datetime.timedelta(days=2))
        page = self.client.get(reverse('patient_dashboard'))
        self.assertContains(page, 'with Marcus Reed')
        self.assertNotContains(page, 'Dr. Marcus')
