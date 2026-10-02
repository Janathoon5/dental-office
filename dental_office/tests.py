import datetime

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
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


class MoneyFilterTests(TestCase):
    def test_thousands_separator_and_negative_sign(self):
        from decimal import Decimal
        from dental_office.templatetags.office import money
        self.assertEqual(money(Decimal('4405')), '$4,405.00')
        self.assertEqual(money(Decimal('-9953.5')), '-$9,953.50')
        self.assertEqual(money(36), '$36.00')
        self.assertEqual(money(None), '')

    def test_invoice_pages_use_it(self):
        patient = Patient.objects.create(first_name='M', last_name='F', phone='1', date_of_birth=datetime.date(1990, 1, 1))
        invoice = Invoice.objects.create(patient=patient, subtotal=4405, insurance_amount=0)
        self.client.force_login(make_staff('deskmoney', 'receptionist'))
        self.assertContains(self.client.get(reverse('invoice_detail', args=[invoice.pk])), '$4,405.00')
        self.assertContains(self.client.get(reverse('invoice_list')), '$4,405.00')


class ClientIPTests(TestCase):
    """Behind Railway's proxy, REMOTE_ADDR is the proxy and changes between
    requests; the visitor's address is the last public one in
    X-Forwarded-For."""

    def _ip(self, forwarded=None, remote='100.64.0.7'):
        from django.test import RequestFactory
        from dental_office.security import client_ip
        extra = {'REMOTE_ADDR': remote}
        if forwarded is not None:
            extra['HTTP_X_FORWARDED_FOR'] = forwarded
        return client_ip(RequestFactory().get('/', **extra))

    def test_reads_the_visitor_address_added_by_the_proxy(self):
        self.assertEqual(self._ip('81.2.69.142'), '81.2.69.142')
        self.assertEqual(self._ip('81.2.69.142, 10.0.0.5'), '81.2.69.142')

    def test_a_typed_in_address_can_not_hide_the_real_one(self):
        self.assertEqual(self._ip('1.2.3.4, 81.2.69.142'), '81.2.69.142')
        self.assertEqual(self._ip('not-an-ip, 81.2.69.142'), '81.2.69.142')

    def test_falls_back_to_the_connection_address(self):
        self.assertEqual(self._ip(None, remote='127.0.0.1'), '127.0.0.1')


class LoginLockoutTests(TestCase):
    """Regression guard: on the live server every attempt came from a
    different proxy address, so wrong passwords never locked an account."""

    def setUp(self):
        User.objects.create_user('lockme', password='right-password')

    def _attempt(self, n, visitor='81.2.69.142'):
        return self.client.post(reverse('login'), {'username': 'lockme', 'password': 'wrong'},
                                REMOTE_ADDR=f'100.64.0.{n}', HTTP_X_FORWARDED_FOR=visitor)

    def test_five_wrong_passwords_lock_the_account_with_a_clear_message(self):
        responses = [self._attempt(n) for n in range(1, 6)]
        self.assertEqual(responses[0].status_code, 200)
        self.assertEqual(responses[-1].status_code, 429)
        self.assertContains(responses[-1], 'Too many incorrect sign-in attempts', status_code=429)
        # Locked even with the right password now.
        response = self.client.post(reverse('login'), {'username': 'lockme', 'password': 'right-password'},
                                    REMOTE_ADDR='100.64.0.9', HTTP_X_FORWARDED_FOR='81.2.69.142')
        self.assertEqual(response.status_code, 429)

    def test_someone_else_is_not_locked_out(self):
        for n in range(1, 6):
            self._attempt(n)
        response = self.client.post(reverse('login'), {'username': 'lockme', 'password': 'right-password'},
                                    HTTP_X_FORWARDED_FOR='81.2.69.200')
        self.assertEqual(response.status_code, 302)


class FriendlyErrorPageTests(TestCase):
    def test_missing_page_has_a_way_back(self):
        response = self.client.get('/no-such-page/')
        self.assertContains(response, 'Page not found', status_code=404)
        self.assertContains(response, 'href="/"', status_code=404)

    @override_settings(RATELIMIT_ENABLE=True)
    def test_too_many_requests_page(self):
        url = reverse('appointment_request')
        for n in range(10):
            self.client.get(url, REMOTE_ADDR=f'100.64.1.{n}', HTTP_X_FORWARDED_FOR='81.2.69.77')
        response = self.client.get(url, REMOTE_ADDR='100.64.1.99', HTTP_X_FORWARDED_FOR='81.2.69.77')
        self.assertContains(response, 'Please wait a moment', status_code=429)


class RolePageTests(TestCase):
    def test_dentist_only_page_explains_the_bounce(self):
        self.client.force_login(make_staff('deskrole', 'receptionist'))
        response = self.client.get(reverse('reports'), follow=True)
        self.assertEqual(response.redirect_chain[-1][0], reverse('dashboard'))
        self.assertContains(response, 'Only dentists can open that page.')

    def test_hygienist_dashboard_has_their_schedule_and_badge(self):
        hygienist = make_staff('hygdash', 'hygienist')
        patient = Patient.objects.create(first_name='H', last_name='D', phone='1', date_of_birth=datetime.date(1990, 1, 1))
        from appointments.models import Appointment
        from django.utils import timezone
        Appointment.objects.create(patient=patient, dentist=hygienist, date=timezone.localdate(),
                                   start_time=datetime.time(9, 0), appointment_type='cleaning')
        self.client.force_login(hygienist)
        page = self.client.get(reverse('dashboard'))
        self.assertContains(page, 'My Schedule Today')
        self.assertContains(page, '>Hygienist</span>')
