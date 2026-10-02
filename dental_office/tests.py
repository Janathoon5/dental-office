import datetime

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from patients.models import Patient
from billing.models import Invoice, Payment
from staff.models import StaffProfile, TOTPDevice


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


def make_staff(username, role):
    user = User.objects.create_user(username=username, password='pw')
    StaffProfile.objects.create(user=user, role=role)
    TOTPDevice.objects.create(user=user, secret='JBSWY3DPEHPK3PXP', confirmed=True)
    return user


class ReportsPageTests(TestCase):
    """Regression guard: the revenue chart's insurance series was never passed
    to the page, which broke the script that draws both charts."""

    def test_every_chart_series_is_filled_in(self):
        patient = Patient.objects.create(first_name='R', last_name='P', phone='1', date_of_birth=datetime.date(1990, 1, 1))
        Invoice.objects.create(patient=patient, subtotal=1500, insurance_amount=1150)
        self.client.force_login(make_staff('drreports', 'dentist'))
        page = self.client.get(reverse('reports')).content.decode()
        self.assertNotIn('data: ,', page)
        self.assertIn('data: [1150.0]', page)


class AdminRedirectTests(TestCase):
    """Regression guard: logged-in non-admins visiting /admin/ used to bounce
    between the admin and its login page until the browser gave up."""

    def test_patient_is_sent_to_their_portal(self):
        user = User.objects.create_user('pt', password='pw')
        user.groups.add(Group.objects.get_or_create(name='Patient')[0])
        Patient.objects.create(first_name='P', last_name='T', phone='1', date_of_birth=datetime.date(1990, 1, 1), user=user)
        self.client.force_login(user)
        response = self.client.get('/admin/', follow=True)
        self.assertEqual(response.redirect_chain[-1][0], reverse('patient_dashboard'))
        self.assertContains(response, 'only for site administrators')

    def test_staff_who_are_not_admins_go_to_the_dashboard(self):
        self.client.force_login(make_staff('deskadmin', 'receptionist'))
        response = self.client.get('/admin/', follow=True)
        self.assertEqual(response.redirect_chain[-1][0], reverse('dashboard'))
        self.assertLess(len(response.redirect_chain), 4)

    def test_admins_still_reach_the_admin(self):
        admin_user = User.objects.create_superuser('owner', 'o@example.com', 'pw')
        TOTPDevice.objects.create(user=admin_user, secret='JBSWY3DPEHPK3PXP', confirmed=True)
        self.client.force_login(admin_user)
        self.assertEqual(self.client.get('/admin/').status_code, 200)

    def test_logged_out_visitors_go_to_the_app_login(self):
        response = self.client.get('/admin/', follow=True)
        self.assertEqual(response.redirect_chain[-1][0], reverse('login') + '?next=/admin/')
