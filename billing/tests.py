import datetime

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from patients.models import Patient
from staff.models import StaffProfile
from .models import Invoice


class BillingAccessControlTests(TestCase):
    """Regression guard for the cross-patient IDOR bug: these views must be
    staff-only, since patient portal accounts are also plain authenticated
    Users and must not be able to browse other patients' invoices/payments."""

    def setUp(self):
        self.other_patient = Patient.objects.create(
            first_name='Other', last_name='Patient',
            date_of_birth=datetime.date(1990, 1, 1), phone='555-0000',
        )
        self.invoice = Invoice.objects.create(patient=self.other_patient, subtotal=100)

        self.patient_user = User.objects.create_user(username='patientuser', password='testpass123')
        patient_group, _ = Group.objects.get_or_create(name='Patient')
        self.patient_user.groups.add(patient_group)

        self.staff_user = User.objects.create_user(username='staffuser', password='testpass123')
        StaffProfile.objects.create(user=self.staff_user, role='dentist')

    def _get_urls(self):
        return [
            reverse('invoice_list'),
            reverse('invoice_add'),
            reverse('invoice_detail', args=[self.invoice.pk]),
            reverse('invoice_edit', args=[self.invoice.pk]),
            reverse('payment_add', args=[self.invoice.pk]),
        ]

    def test_patient_account_is_blocked_from_every_staff_view(self):
        self.client.login(username='patientuser', password='testpass123')
        for url in self._get_urls():
            response = self.client.get(url)
            self.assertEqual(
                response.status_code, 302,
                f'{url} should redirect a patient-role account, got {response.status_code}',
            )

    def test_staff_account_can_reach_get_views(self):
        self.client.login(username='staffuser', password='testpass123')
        for url in (reverse('invoice_list'), reverse('invoice_add'),
                    reverse('invoice_detail', args=[self.invoice.pk]),
                    reverse('invoice_edit', args=[self.invoice.pk])):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, f'{url} should be reachable by staff')
