import io
import shutil
import tempfile
from unittest import mock

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from appointments.models import ScheduledJobRun
from appointments.recalls import recall_lists
from billing.models import AIUsage, ClaimDenial, Invoice
from patients.models import Patient
from staff.models import StaffProfile, TOTPDevice


class MediaMixin:
    def setUp(self):
        super().setUp()
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        overrides = override_settings(MEDIA_ROOT=media)
        overrides.enable()
        self.addCleanup(overrides.disable)


class ResetDemoTests(MediaMixin, TestCase):
    def test_refuses_to_wipe_unless_demo_mode(self):
        Patient.objects.create(first_name='Real', last_name='Patient', phone='1', date_of_birth='1990-01-01')
        with override_settings(DEMO_MODE=False):
            with self.assertRaises(CommandError):
                call_command('reset_demo', stdout=io.StringIO())
        self.assertTrue(Patient.objects.filter(first_name='Real').exists())

    @override_settings(DEMO_MODE=True)
    def test_reset_rebuilds_the_same_practice_and_keeps_real_accounts(self):
        owner = User.objects.create_superuser('owner', 'o@example.com', 'pw')
        staff = User.objects.create_user('realstaff', password='pw')
        StaffProfile.objects.create(user=staff, role='dentist')
        Patient.objects.create(first_name='Made', last_name='Up', phone='1', date_of_birth='1990-01-01')
        portal = User.objects.create_user('someportal', password='pw')
        portal.groups.add(Group.objects.get_or_create(name='Patient')[0])

        for _ in range(2):
            call_command('reset_demo', stdout=io.StringIO())
            self.assertEqual(Patient.objects.count(), 20)
            self.assertEqual(ClaimDenial.objects.count(), 4)
            self.assertEqual(User.objects.filter(username__startswith='demo-').count(), 4)

        self.assertFalse(Patient.objects.filter(first_name='Made').exists())
        self.assertTrue(User.objects.filter(pk=owner.pk).exists())
        self.assertTrue(User.objects.filter(pk=staff.pk).exists())
        self.assertFalse(User.objects.filter(username='someportal').exists())

        lists = recall_lists()
        self.assertEqual({i['patient'].first_name for i in lists['overdue']}, {'Carlos', 'Linda', 'James'})
        self.assertEqual({i['patient'].first_name for i in lists['never']}, {'Tom'})
        maria = Patient.objects.get(first_name='Maria')
        self.assertEqual(maria.user.username, 'demo-patient')
        self.assertEqual(str(Invoice.objects.get(patient=maria).subtotal), '1750.00')

    @override_settings(DEMO_MODE=True)
    def test_daily_job_resets_demo_then_sends_emails(self):
        call_command('run_daily_jobs', stdout=io.StringIO())
        self.assertEqual(Patient.objects.count(), 20)
        self.assertTrue(ScheduledJobRun.objects.get().succeeded)


@override_settings(DEMO_MODE=True, REQUIRE_2FA=False)
class DemoLoginTests(MediaMixin, TestCase):
    def setUp(self):
        super().setUp()
        call_command('reset_demo', stdout=io.StringIO())

    def test_login_page_offers_demo_roles(self):
        page = self.client.get(reverse('login'))
        for role in ('dentist', 'frontdesk', 'hygienist', 'patient'):
            self.assertContains(page, reverse('demo_login', args=[role]))

    def test_every_role_can_browse_its_pages(self):
        maria = Patient.objects.get(first_name='Maria')
        denial = ClaimDenial.objects.get(invoice__patient=maria)
        pages = {
            'dentist': ['/', reverse('patient_detail', args=[maria.pk]), reverse('tooth_chart', args=[maria.pk]),
                        reverse('recall_list'), reverse('denial_list'), reverse('denial_detail', args=[denial.pk]),
                        reverse('denial_review', args=[denial.pk]), reverse('denial_packet', args=[denial.pk]),
                        reverse('invoice_detail', args=[denial.invoice.pk])],
            'frontdesk': ['/', reverse('reminders_dashboard'), reverse('invoice_list'), reverse('request_list'),
                          reverse('supply_list')],
            'hygienist': ['/', reverse('appointment_list')],
            'patient': [reverse('patient_dashboard')],
        }
        for role, urls in pages.items():
            self.client.logout()
            response = self.client.post(reverse('demo_login', args=[role]))
            self.assertEqual(response.status_code, 302, role)
            for url in urls:
                page = self.client.get(url)
                self.assertEqual(page.status_code, 200, f'{role} {url}')
                self.assertContains(page, 'demo practice')

    def test_packet_pdf_builds_from_demo_data(self):
        denial = ClaimDenial.objects.get(invoice__patient__first_name='Maria')
        self.client.post(reverse('demo_login', args=['dentist']))
        response = self.client.post(reverse('denial_packet', args=[denial.pk]), {'summary': 'on', 'original': 'on'})
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_demo_accounts_cannot_reset_or_reach_admin(self):
        self.client.post(reverse('demo_login', args=['dentist']))
        self.assertEqual(self.client.post(reverse('reset_demo')).status_code, 404)
        self.assertNotEqual(self.client.get('/admin/').status_code, 200)

    def test_superuser_can_reset(self):
        owner = User.objects.create_superuser('owner', 'o@example.com', 'pw')
        self.client.force_login(owner)
        Patient.objects.filter(first_name='Maria').update(phone='changed')
        self.client.post(reverse('reset_demo'))
        self.assertNotEqual(Patient.objects.get(first_name='Maria').phone, 'changed')


class DemoOffTests(TestCase):
    def test_demo_login_does_not_exist_outside_demo_mode(self):
        self.assertEqual(self.client.post(reverse('demo_login', args=['dentist'])).status_code, 404)
        self.assertNotContains(self.client.get(reverse('login')), 'Just looking around?')


class TwoFactorSwitchTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('desk', password='pw')
        StaffProfile.objects.create(user=self.staff, role='receptionist')
        self.client.force_login(self.staff)

    @override_settings(REQUIRE_2FA=True)
    def test_required_by_default(self):
        self.assertRedirects(self.client.get('/'), reverse('setup_2fa'), fetch_redirect_response=False)

    @override_settings(REQUIRE_2FA=False)
    def test_can_be_switched_off(self):
        self.assertEqual(self.client.get('/').status_code, 200)

    @override_settings(REQUIRE_2FA=False)
    def test_accounts_with_2fa_still_get_asked_for_a_code(self):
        TOTPDevice.objects.create(user=self.staff, secret='JBSWY3DPEHPK3PXP', confirmed=True)
        self.staff.set_password('pw')
        self.staff.save()
        self.client.logout()
        response = self.client.post(reverse('login'), {'username': 'desk', 'password': 'pw'})
        self.assertRedirects(response, reverse('verify_otp'), fetch_redirect_response=False)


class AIDailyLimitTests(MediaMixin, TestCase):
    def setUp(self):
        super().setUp()
        patient = Patient.objects.create(first_name='A', last_name='B', phone='1', date_of_birth='1990-01-01')
        self.invoice = Invoice.objects.create(patient=patient, subtotal=100)
        self.staff = User.objects.create_user('desk', password='pw')
        StaffProfile.objects.create(user=self.staff, role='receptionist')
        TOTPDevice.objects.create(user=self.staff, secret='JBSWY3DPEHPK3PXP', confirmed=True)

    def _upload(self):
        return self.client.post(reverse('denial_upload', args=[self.invoice.pk]), {
            'letter': SimpleUploadedFile('l.pdf', b'%PDF-1.4'), 'confirm_no_phi': 'on',
        })

    @override_settings(AI_DAILY_LIMIT=2, ANTHROPIC_API_KEY='')
    def test_cap_blocks_staff_but_not_superusers(self):
        AIUsage.objects.create(task='analyze')
        AIUsage.objects.create(task='analyze')
        self.client.force_login(self.staff)
        self._upload()
        self.assertFalse(ClaimDenial.objects.exists())
        self.assertContains(self.client.get(reverse('invoice_detail', args=[self.invoice.pk])), "AI limit")

        owner = User.objects.create_superuser('owner', 'o@example.com', 'pw')
        TOTPDevice.objects.create(user=owner, secret='JBSWY3DPEHPK3PXP', confirmed=True)
        self.client.force_login(owner)
        # A run that works is counted (a failed one is given back).
        working_ai = {'analyze': (lambda denial: {}, lambda denial, result: None)}
        with mock.patch.dict('billing.ai.TASKS', working_ai):
            self._upload()
        self.assertEqual(ClaimDenial.objects.count(), 1)
        self.assertEqual(AIUsage.objects.count(), 3)

    @override_settings(AI_DAILY_LIMIT=0, ANTHROPIC_API_KEY='')
    def test_no_cap_by_default(self):
        for _ in range(3):
            AIUsage.objects.create(task='analyze')
        self.client.force_login(self.staff)
        self._upload()
        self.assertEqual(ClaimDenial.objects.count(), 1)


class DemoPatientHistoryTests(MediaMixin, TestCase):
    """From the live-site test: Reports said "New Patients This Month: 21"
    because every demo patient was created on the day of the reset."""

    @override_settings(DEMO_MODE=True)
    def test_only_one_demo_patient_is_new_this_month(self):
        from django.utils import timezone
        call_command('reset_demo', stdout=io.StringIO())
        today = timezone.localdate()
        new = Patient.objects.filter(created_at__year=today.year, created_at__month=today.month)
        self.assertEqual([p.first_name for p in new], ['Tom'])
