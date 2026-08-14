import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from patients.models import Patient
from billing.models import Invoice, Payment


class SoftDeleteAdminFieldsTests(TestCase):
    """Regression guard: is_active/deleted_at/deleted_by must not be plain
    editable fields on SoftDeleteModel admin forms (main ModelAdmin or
    inline). Editable, they let a normal save silently flip is_active off
    without ever going through delete() — no deleted_at/deleted_by gets
    recorded, defeating the audit trail the soft-delete system exists for."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(username='admintest', password='testpass123')
        self.client.force_login(self.superuser)
        self.patient = Patient.objects.create(
            first_name='Admin', last_name='Fields',
            date_of_birth=datetime.date(1990, 1, 1), phone='555-0000',
        )
        self.invoice = Invoice.objects.create(patient=self.patient, subtotal=200, insurance_amount=50)
        self.payment = Payment.objects.create(invoice=self.invoice, amount=75, method='cash')

    def test_is_active_not_rendered_as_editable_input_on_main_form(self):
        response = self.client.get(reverse('admin:patients_patient_change', args=[self.patient.pk]))
        self.assertNotContains(response, '<input type="checkbox" name="is_active"')

    def test_is_active_not_rendered_as_editable_input_on_payment_inline(self):
        response = self.client.get(reverse('admin:billing_invoice_change', args=[self.invoice.pk]))
        self.assertNotContains(response, 'name="payments-0-is_active"')

    def test_saving_invoice_change_form_does_not_flip_existing_payment_inactive(self):
        """The exact bug: editing an Invoice and saving (a completely
        ordinary admin action) used to soft-delete every Payment inline row,
        because the un-submitted is_active checkbox defaulted to unchecked."""
        prefix = 'payments-'
        response = self.client.post(
            reverse('admin:billing_invoice_change', args=[self.invoice.pk]),
            {
                'patient': self.patient.pk, 'appointment': '', 'date_issued_0': '2026-08-01',
                'subtotal': '200', 'insurance_amount': '50', 'status': 'pending', 'notes': '',
                f'{prefix}TOTAL_FORMS': '1', f'{prefix}INITIAL_FORMS': '1',
                f'{prefix}MIN_NUM_FORMS': '0', f'{prefix}MAX_NUM_FORMS': '1000',
                f'{prefix}0-id': self.payment.pk, f'{prefix}0-invoice': self.invoice.pk,
                f'{prefix}0-amount': str(self.payment.amount), f'{prefix}0-method': self.payment.method,
                f'{prefix}0-notes': self.payment.notes,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.payment.refresh_from_db()
        self.assertTrue(self.payment.is_active)
        self.assertIsNone(self.payment.deleted_at)
