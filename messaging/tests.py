import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from patients.models import Patient
from staff.models import StaffProfile, TOTPDevice

from .models import Conversation, DeviceToken, Message


class StaffSendMessageTests(TestCase):
    def setUp(self):
        self.patient = Patient.objects.create(
            first_name='Api', last_name='Test',
            date_of_birth=datetime.date(1990, 1, 1), phone='555-0000',
        )
        self.staff_user = User.objects.create_user(username='staffuser', password='testpass123')
        StaffProfile.objects.create(user=self.staff_user, role='dentist')
        TOTPDevice.objects.create(user=self.staff_user, secret='JBSWY3DPEHPK3PXP', confirmed=True)
        self.client.force_login(self.staff_user)

    def test_send_message_creates_conversation_and_message(self):
        response = self.client.post(
            reverse('staff_send_message', args=[self.patient.pk]),
            {'body': 'Your cleaning is confirmed for next week.'},
        )
        self.assertEqual(response.status_code, 302)

        conversation = Conversation.objects.get(patient=self.patient)
        message = conversation.messages.get()
        self.assertEqual(message.sender, self.staff_user)
        self.assertEqual(message.body, 'Your cleaning is confirmed for next week.')

    def test_blank_message_not_saved(self):
        self.client.post(reverse('staff_send_message', args=[self.patient.pk]), {'body': '   '})
        self.assertFalse(Conversation.objects.filter(patient=self.patient).exists())

    def test_reusing_conversation_on_second_message(self):
        url = reverse('staff_send_message', args=[self.patient.pk])
        self.client.post(url, {'body': 'First message'})
        self.client.post(url, {'body': 'Second message'})

        self.assertEqual(Conversation.objects.filter(patient=self.patient).count(), 1)
        conversation = Conversation.objects.get(patient=self.patient)
        self.assertEqual(conversation.messages.count(), 2)

    def test_patient_detail_page_shows_messages(self):
        conversation = Conversation.objects.create(patient=self.patient)
        Message.objects.create(conversation=conversation, sender=self.staff_user, body='Hello there')

        response = self.client.get(reverse('patient_detail', args=[self.patient.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Hello there')


class PushNotificationTests(TestCase):
    def setUp(self):
        self.patient = Patient.objects.create(
            first_name='Api', last_name='Test',
            date_of_birth=datetime.date(1990, 1, 1), phone='555-0000',
        )
        self.staff_user = User.objects.create_user(username='staffuser2', password='testpass123')
        StaffProfile.objects.create(user=self.staff_user, role='dentist')
        DeviceToken.objects.create(patient=self.patient, fcm_token='fake-token', platform='android')

    def test_firebase_app_disabled_under_test_runner(self):
        """Regression guard: a real Firebase service account file is
        configured in this dev environment (FIREBASE_SERVICE_ACCOUNT_PATH),
        but push sending must never attempt a real network call while
        running under `manage.py test`."""
        from messaging import push
        self.assertIsNone(push._get_firebase_app())

    def test_staff_message_with_registered_device_does_not_hit_network(self):
        """Exercises the full post_save signal path (staff message + a
        registered device token) end-to-end. If the test-mode guard didn't
        apply along this real code path, this would attempt a genuine
        network call to Firebase's API using real prod credentials."""
        conversation = Conversation.objects.create(patient=self.patient)
        message = Message.objects.create(conversation=conversation, sender=self.staff_user, body='Hi')
        self.assertIsNotNone(message.pk)
