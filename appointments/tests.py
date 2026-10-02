import io
import datetime

from django.core import mail
from django.core.management import call_command

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


def weekday_at_least(days):
    """The first Monday-Friday at least `days` from today, so a 10 AM test
    booking is inside office hours whatever day the tests run."""
    day = timezone_today_plus(days)
    while day.weekday() >= 5:
        day += datetime.timedelta(days=1)
    return day


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
        self.date = weekday_at_least(3)
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
        self.assertEqual(statuses[-1], 429)


class RecallTests(TestCase):
    """Recall due dates come from the last *completed* cleaning/checkup plus
    the patient's interval; anyone already booked drops off the list."""

    def setUp(self):
        from django.utils import timezone
        self.today = timezone.localdate()

    def _patient(self, name, email='p@example.com', interval=6):
        return Patient.objects.create(
            first_name=name, last_name='Test', date_of_birth=datetime.date(1990, 1, 1),
            phone='555-0000', email=email, recall_interval_months=interval,
        )

    def _appt(self, patient, days_from_today, status='completed', appt_type='cleaning'):
        return Appointment.objects.create(
            patient=patient, date=self.today + datetime.timedelta(days=days_from_today),
            start_time=datetime.time(9, 0), status=status, appointment_type=appt_type,
        )

    def test_add_months_clamps_to_month_end(self):
        from .recalls import add_months
        self.assertEqual(add_months(datetime.date(2025, 8, 31), 6), datetime.date(2026, 2, 28))
        self.assertEqual(add_months(datetime.date(2025, 11, 15), 3), datetime.date(2026, 2, 15))

    def test_patients_are_grouped_correctly(self):
        from .recalls import recall_lists
        overdue = self._patient('Overdue')
        self._appt(overdue, -250)
        soon = self._patient('Soon')
        self._appt(soon, -170)
        fine = self._patient('Fine')
        self._appt(fine, -30)
        booked = self._patient('Booked')
        self._appt(booked, -250)
        self._appt(booked, 5, status='scheduled')
        never = self._patient('Never')
        cancelled_only = self._patient('CancelledOnly')
        self._appt(cancelled_only, -250, status='cancelled')
        filling_only = self._patient('FillingOnly')
        self._appt(filling_only, -250, appt_type='filling')

        lists = recall_lists(self.today)
        names = {k: {i['patient'].first_name for i in v} for k, v in lists.items()}
        self.assertEqual(names['overdue'], {'Overdue'})
        self.assertEqual(names['due_soon'], {'Soon'})
        self.assertEqual(names['never'], {'Never', 'CancelledOnly', 'FillingOnly'})

    def test_interval_changes_due_date(self):
        from .recalls import recall_lists
        p = self._patient('Quarterly', interval=3)
        self._appt(p, -100)
        overdue = recall_lists(self.today)['overdue']
        self.assertEqual([i['patient'] for i in overdue], [p])

    def test_recall_email_sent_once_per_cycle(self):
        from django.core import mail
        from django.core.management import call_command
        from .models import RecallNotice
        p = self._patient('Overdue')
        self._appt(p, -250)
        no_email = self._patient('NoEmail', email='')
        self._appt(no_email, -250)

        call_command('send_recall_reminders', stdout=io.StringIO())
        call_command('send_recall_reminders', stdout=io.StringIO())

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['p@example.com'])
        self.assertEqual(RecallNotice.objects.filter(patient=p, status='sent').count(), 1)

    def test_recall_pages_render_for_staff_only(self):
        staff = User.objects.create_user(username='staffrecall', password='testpass123')
        StaffProfile.objects.create(user=staff, role='dentist')
        TOTPDevice.objects.create(user=staff, secret='JBSWY3DPEHPK3PXP', confirmed=True)
        p = self._patient('Overdue')
        self._appt(p, -250)

        patient_user = User.objects.create_user(username='patrecall', password='testpass123')
        patient_user.groups.add(Group.objects.get_or_create(name='Patient')[0])
        self.client.force_login(patient_user)
        self.assertEqual(self.client.get(reverse('recall_list')).status_code, 302)
        self.assertEqual(self.client.post(reverse('send_recalls_now')).status_code, 302)

        self.client.force_login(staff)
        for show in ('overdue', 'due_soon', 'never', 'bogus'):
            response = self.client.get(reverse('recall_list'), {'show': show})
            self.assertEqual(response.status_code, 200)
        self.assertContains(self.client.get(reverse('recall_list')), 'Overdue Test')
        self.assertContains(self.client.get(reverse('patient_detail', args=[p.pk])), 'Overdue')
        self.assertContains(self.client.get(reverse('dashboard')), 'Overdue Cleanings')


class DailyEmailJobTests(TestCase):
    """send_daily_emails is what the Railway cron service runs every morning."""

    def setUp(self):
        from django.utils import timezone
        today = timezone.localdate()
        tomorrow_patient = Patient.objects.create(first_name='Tomorrow', last_name='Test', phone='1',
                                                  date_of_birth=datetime.date(1990, 1, 1), email='t@example.com')
        Appointment.objects.create(patient=tomorrow_patient, date=today + datetime.timedelta(days=1),
                                   start_time=datetime.time(9, 0))
        overdue_patient = Patient.objects.create(first_name='Overdue', last_name='Test', phone='2',
                                                 date_of_birth=datetime.date(1990, 1, 1), email='o@example.com')
        Appointment.objects.create(patient=overdue_patient, date=today - datetime.timedelta(days=250),
                                   start_time=datetime.time(9, 0), status='completed', appointment_type='cleaning')

    def test_sends_reminders_and_recalls_once_and_records_the_run(self):
        from django.core import mail
        from django.core.management import call_command
        from .models import ScheduledJobRun

        call_command('send_daily_emails', stdout=io.StringIO())
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ['o@example.com', 't@example.com'])
        run = ScheduledJobRun.objects.get()
        self.assertTrue(run.succeeded)
        self.assertEqual(run.summary, 'Appointment reminders: 1 sent, 0 already sent, 0 without an email address, 0 failed\n'
                                      'Cleaning recalls: 1 sent, 0 already sent, 0 without an email address, 0 failed')

        # Running again the same day sends nothing new.
        call_command('send_daily_emails', stdout=io.StringIO())
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(ScheduledJobRun.objects.count(), 2)

    def test_one_failing_job_does_not_stop_the_other(self):
        from unittest import mock
        from django.core import mail
        from django.core.management import CommandError, call_command
        from django.core.management import call_command as real_call_command
        from .models import ScheduledJobRun

        def fake(name, *args, **kwargs):
            if name == 'send_reminders':
                raise RuntimeError('boom')
            return real_call_command(name, *args, **kwargs)

        with mock.patch('appointments.management.commands.send_daily_emails.call_command', side_effect=fake):
            with self.assertRaises(CommandError):
                call_command('send_daily_emails', stdout=io.StringIO())
        run = ScheduledJobRun.objects.get()
        self.assertFalse(run.succeeded)
        self.assertIn('Appointment reminders: FAILED (boom)', run.summary)
        self.assertEqual([m.to[0] for m in mail.outbox], ['o@example.com'])

    def test_status_card_shows_last_run_and_overdue(self):
        from django.utils import timezone
        from .models import ScheduledJobRun
        staff = User.objects.create_user(username='desk', password='testpass123')
        StaffProfile.objects.create(user=staff, role='receptionist')
        TOTPDevice.objects.create(user=staff, secret='JBSWY3DPEHPK3PXP', confirmed=True)
        self.client.force_login(staff)

        for url in (reverse('reminders_dashboard'), reverse('recall_list')):
            self.assertContains(self.client.get(url), 'No automatic run recorded yet')

        run = ScheduledJobRun.objects.create(summary='Cleaning recalls: Recall emails: 3 sent')
        page = self.client.get(reverse('reminders_dashboard'))
        self.assertContains(page, 'Running')
        self.assertContains(page, '3 sent')

        ScheduledJobRun.objects.filter(pk=run.pk).update(ran_at=timezone.now() - datetime.timedelta(hours=30))
        self.assertContains(self.client.get(reverse('recall_list')), "hasn't run in over a day")


class AppointmentFormFixesTests(TestCase):
    """Regression guards from the live-site test: past appointments must be
    editable, and every form error must reach the screen."""

    def setUp(self):
        from django.utils import timezone
        self.today = timezone.localdate()
        self.patient = Patient.objects.create(first_name='Fix', last_name='Patient',
                                              date_of_birth=datetime.date(1990, 1, 1), phone='555-0000')
        self.other = Patient.objects.create(first_name='Other', last_name='Patient',
                                            date_of_birth=datetime.date(1990, 1, 1), phone='555-0001')
        self.dentist = User.objects.create_user('drfix', password='pw', first_name='Elena', last_name='Park')
        StaffProfile.objects.create(user=self.dentist, role='dentist')
        self.staff = User.objects.create_user('deskfix', password='pw')
        StaffProfile.objects.create(user=self.staff, role='receptionist')
        TOTPDevice.objects.create(user=self.staff, secret='JBSWY3DPEHPK3PXP', confirmed=True)
        self.client.force_login(self.staff)

    def _data(self, **overrides):
        data = {'patient': self.patient.pk, 'dentist': self.dentist.pk, 'date': self.today.isoformat(),
                'start_time': '10:00', 'duration_minutes': 60, 'appointment_type': 'checkup',
                'status': 'scheduled', 'notes': ''}
        data.update(overrides)
        return data

    def test_double_booking_message_is_shown(self):
        Appointment.objects.create(patient=self.other, dentist=self.dentist, date=self.today,
                                   start_time=datetime.time(10, 0), duration_minutes=60)
        response = self.client.post(reverse('appointment_add'), self._data(start_time='10:15'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already has an appointment')

    def test_bad_duration_message_is_shown(self):
        response = self.client.post(reverse('appointment_add'), self._data(duration_minutes='-30'))
        self.assertContains(response, 'A visit has to be at least 5 minutes long.')

    def test_past_appointment_can_be_marked_completed(self):
        past = Appointment.objects.create(patient=self.patient, dentist=self.dentist,
                                          date=self.today - datetime.timedelta(days=6),
                                          start_time=datetime.time(10, 0), status='no_show')
        form_page = self.client.get(reverse('appointment_edit', args=[past.pk]))
        self.assertNotContains(form_page, f'min="{self.today.isoformat()}"')
        response = self.client.post(reverse('appointment_edit', args=[past.pk]),
                                    self._data(date=past.date.isoformat(), status='completed', notes='Came in late'))
        self.assertRedirects(response, reverse('appointment_detail', args=[past.pk]))
        past.refresh_from_db()
        self.assertEqual((past.status, past.notes), ('completed', 'Came in late'))

    def test_past_dates_still_blocked_for_new_and_moved_appointments(self):
        yesterday = (self.today - datetime.timedelta(days=1)).isoformat()
        response = self.client.post(reverse('appointment_add'), self._data(date=yesterday))
        self.assertContains(response, "can&#x27;t be booked on a past date")
        future = Appointment.objects.create(patient=self.patient, dentist=self.dentist,
                                            date=self.today + datetime.timedelta(days=3), start_time=datetime.time(9, 0))
        response = self.client.post(reverse('appointment_edit', args=[future.pk]), self._data(date=yesterday))
        self.assertContains(response, "can&#x27;t be booked on a past date")

    def test_provider_dropdown_shows_names(self):
        page = self.client.get(reverse('appointment_add'))
        self.assertContains(page, 'Dr. Elena Park (Dentist)')
        self.assertNotContains(page, '>drfix<')


class SendNowMessageTests(TestCase):
    def setUp(self):
        from django.utils import timezone
        self.staff = User.objects.create_user('desksend', password='pw')
        StaffProfile.objects.create(user=self.staff, role='receptionist')
        TOTPDevice.objects.create(user=self.staff, secret='JBSWY3DPEHPK3PXP', confirmed=True)
        self.client.force_login(self.staff)
        patient = Patient.objects.create(first_name='Send', last_name='Now', phone='1', email='s@example.com',
                                         date_of_birth=datetime.date(1990, 1, 1))
        Appointment.objects.create(patient=patient, date=timezone.localdate() + datetime.timedelta(days=1),
                                   start_time=datetime.time(9, 0))

    def test_reminder_result_is_a_readable_sentence_shown_once(self):
        response = self.client.post(reverse('send_reminders_now'), {'days': 1}, follow=True)
        self.assertContains(response, '1 reminder sent.', count=1)
        self.assertNotContains(response, '1,0,0,0')
        response = self.client.post(reverse('send_reminders_now'), {'days': 1}, follow=True)
        self.assertContains(response, '0 reminders sent. 1 already sent.', count=1)

    def test_recall_result_is_a_readable_sentence(self):
        response = self.client.post(reverse('send_recalls_now'), follow=True)
        self.assertContains(response, 'No recall emails were due.', count=1)


def next_weekday(weekday, at_least=1):
    """The next date (at least `at_least` days away) on the given weekday,
    0 = Monday ... 6 = Sunday."""
    day = timezone_today_plus(at_least)
    while day.weekday() != weekday:
        day += datetime.timedelta(days=1)
    return day


class BookingRulesTests(TestCase):
    """From the live-site test: staff could book 0-minute and 10-hour visits,
    Sundays, after closing, and the year 2099."""

    def setUp(self):
        self.patient = Patient.objects.create(first_name='Rule', last_name='Patient',
                                              date_of_birth=datetime.date(1990, 1, 1), phone='555-0000')
        self.dentist = User.objects.create_user('drrules', password='pw', first_name='Elena', last_name='Park')
        StaffProfile.objects.create(user=self.dentist, role='dentist')

    def _form(self, **overrides):
        data = {'patient': self.patient.pk, 'dentist': self.dentist.pk,
                'date': next_weekday(1).isoformat(), 'start_time': '10:00', 'duration_minutes': 60,
                'appointment_type': 'checkup', 'status': 'scheduled', 'notes': ''}
        data.update(overrides)
        return AppointmentForm(data=data)

    def test_normal_weekday_visit_is_fine(self):
        self.assertTrue(self._form().is_valid())

    def test_impossible_lengths_are_blocked(self):
        self.assertIn('at least 5 minutes', str(self._form(duration_minutes=0).errors))
        self.assertIn('at most 4 hours', str(self._form(duration_minutes=600).errors))

    def test_far_future_year_is_blocked(self):
        form = self._form(date='2099-06-02')
        self.assertFalse(form.is_valid())
        self.assertIn('Check the year', str(form.errors['date']))

    def test_outside_hours_needs_book_anyway(self):
        sunday = self._form(date=next_weekday(6).isoformat())
        self.assertFalse(sunday.is_valid())
        self.assertIn('closed on Sundays', str(sunday.errors))
        late = self._form(start_time='16:30')  # a Tuesday visit running to 5:30 PM
        self.assertFalse(late.is_valid())
        self.assertIn('4:30 PM – 5:30 PM', str(late.errors))
        self.assertTrue(self._form(date=next_weekday(6).isoformat(), outside_hours_ok='on').is_valid())

    def test_book_anyway_box_appears_on_the_page(self):
        staff = User.objects.create_user('deskrules', password='pw')
        StaffProfile.objects.create(user=staff, role='receptionist')
        TOTPDevice.objects.create(user=staff, secret='JBSWY3DPEHPK3PXP', confirmed=True)
        self.client.force_login(staff)
        data = {'patient': self.patient.pk, 'dentist': self.dentist.pk, 'date': next_weekday(6).isoformat(),
                'start_time': '10:00', 'duration_minutes': 60, 'appointment_type': 'checkup',
                'status': 'scheduled', 'notes': ''}
        page = self.client.post(reverse('appointment_add'), data)
        self.assertContains(page, 'Book anyway, outside office hours')
        response = self.client.post(reverse('appointment_add'), {**data, 'outside_hours_ok': 'on'})
        self.assertEqual(response.status_code, 302)

    def test_updating_an_existing_out_of_hours_visit_does_not_nag(self):
        appt = Appointment.objects.create(patient=self.patient, dentist=self.dentist, date=next_weekday(6),
                                          start_time=datetime.time(10, 0), duration_minutes=60)
        form = AppointmentForm(instance=appt, data={
            'patient': self.patient.pk, 'dentist': self.dentist.pk, 'date': appt.date.isoformat(),
            'start_time': '10:00', 'duration_minutes': 60, 'appointment_type': 'checkup',
            'status': 'scheduled', 'notes': 'Emergency, approved by Dr. Park'})
        self.assertTrue(form.is_valid(), form.errors)

    def test_public_request_form_follows_office_hours(self):
        response = self.client.post(reverse('appointment_request'), {
            'first_name': 'Pat', 'last_name': 'Lee', 'phone': '(555) 222-3333', 'email': '',
            'preferred_date': next_weekday(6).isoformat(), 'preferred_time': '10:00',
            'appointment_type': 'checkup', 'message': ''})
        self.assertContains(response, 'closed on Sundays')
        self.assertFalse(AppointmentRequest.objects.exists())


class RequestBookingTests(TestCase):
    """From the live-site test: Approve only changed a label. Now it books
    the visit, adds the patient if needed, and emails a confirmation."""

    def setUp(self):
        from billing.models import OfficeSettings
        office = OfficeSettings.load()
        office.office_name, office.phone = 'Bright Smiles Dental', '(555) 010-4567'
        office.address = '123 Main St\nSpringfield, IL 62701'
        office.save()
        self.dentist = User.objects.create_user('drbook', password='pw', first_name='Elena', last_name='Park')
        StaffProfile.objects.create(user=self.dentist, role='dentist')
        self.staff = User.objects.create_user('deskbook', password='pw')
        StaffProfile.objects.create(user=self.staff, role='receptionist')
        TOTPDevice.objects.create(user=self.staff, secret='JBSWY3DPEHPK3PXP', confirmed=True)
        self.client.force_login(self.staff)
        self.day = next_weekday(2)
        self.req = AppointmentRequest.objects.create(
            first_name='Olivia', last_name='Grant', phone='(555) 010-2233', email='olivia@example.com',
            preferred_date=self.day, preferred_time=datetime.time(10, 0), appointment_type='consultation',
            message='Chipped front tooth')

    def _book(self, **overrides):
        data = {'patient_choice': 'new', 'new-first_name': 'Olivia', 'new-last_name': 'Grant',
                'new-date_of_birth': '1992-04-18', 'new-phone': '(555) 010-2233', 'new-email': 'olivia@example.com',
                'date': self.day.isoformat(), 'start_time': '10:00', 'duration_minutes': 60,
                'appointment_type': 'consultation', 'status': 'scheduled', 'dentist': self.dentist.pk,
                'notes': 'Chipped front tooth'}
        data.update(overrides)
        return self.client.post(reverse('request_book', args=[self.req.pk]), data)

    def test_page_is_filled_in_from_the_request(self):
        page = self.client.get(reverse('request_book', args=[self.req.pk]))
        self.assertContains(page, f'value="{self.day.isoformat()}"')
        self.assertContains(page, 'value="Olivia"')
        self.assertContains(page, 'Chipped front tooth')

    def test_booking_a_new_patient(self):
        response = self._book()
        appt = Appointment.objects.get()
        self.assertRedirects(response, reverse('appointment_detail', args=[appt.pk]))
        patient = Patient.objects.get(first_name='Olivia')
        self.assertEqual((appt.patient, appt.date, appt.start_time), (patient, self.day, datetime.time(10, 0)))
        self.req.refresh_from_db()
        self.assertEqual((self.req.status, self.req.patient, self.req.appointment), ('approved', patient, appt))
        email = mail.outbox[0]
        self.assertEqual(email.to, ['olivia@example.com'])
        self.assertIn('Bright Smiles Dental', email.from_email)
        self.assertIn('is confirmed', email.subject)
        self.assertIn(f'{self.day:%B} {self.day.day}, {self.day.year}', email.body)
        self.assertIn('(555) 010-4567', email.body)
        self.assertIn('Dr. Elena Park', email.body)
        page = self.client.get(reverse('request_list'))
        self.assertContains(page, 'Booked ')

    def test_new_patient_needs_a_birth_date(self):
        response = self._book(**{'new-date_of_birth': ''})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Appointment.objects.exists())
        self.assertFalse(Patient.objects.exists())

    def test_existing_patient_is_suggested_and_used(self):
        patient = Patient.objects.create(first_name='Olivia', last_name='Grant', date_of_birth=datetime.date(1992, 4, 18),
                                         phone='555.010.2233', email='')
        page = self.client.get(reverse('request_book', args=[self.req.pk]))
        self.assertContains(page, f'value="{patient.pk}" checked')
        self._book(patient_choice=str(patient.pk))
        self.assertEqual(Patient.objects.count(), 1)
        self.assertEqual(Appointment.objects.get().patient, patient)

    def test_double_booking_still_blocked(self):
        other = Patient.objects.create(first_name='Busy', last_name='Slot', phone='555-0000',
                                       date_of_birth=datetime.date(1980, 1, 1))
        Appointment.objects.create(patient=other, dentist=self.dentist, date=self.day, start_time=datetime.time(10, 0))
        response = self._book()
        self.assertContains(response, 'already has an appointment')
        self.assertEqual(Appointment.objects.count(), 1)
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, 'pending')

    def test_old_approve_button_no_longer_approves_without_booking(self):
        self.client.post(reverse('request_update', args=[self.req.pk]), {'status': 'approved'})
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, 'pending')

    def test_handled_requests_can_not_be_booked_twice(self):
        self.req.status = 'declined'
        self.req.save()
        response = self.client.get(reverse('request_book', args=[self.req.pk]), follow=True)
        self.assertContains(response, 'already declined')


class PatientEmailContentTests(TestCase):
    """From the live-site test: emails had no office name or phone number,
    and dates read "October 02"."""

    def setUp(self):
        from billing.models import OfficeSettings
        office = OfficeSettings.load()
        office.office_name, office.phone = 'Bright Smiles Dental', '(555) 010-4567'
        office.address = '123 Main St\nSpringfield, IL 62701'
        office.save()
        self.patient = Patient.objects.create(first_name='Nora', last_name='Kelly', phone='555-0000',
                                              email='nora@example.com', date_of_birth=datetime.date(1954, 7, 7))

    def test_reminder_names_the_office_and_how_to_reach_it(self):
        day = timezone_today_plus(1)
        Appointment.objects.create(patient=self.patient, date=day, start_time=datetime.time(9, 0))
        call_command('send_reminders', stdout=io.StringIO())
        email = mail.outbox[0]
        self.assertTrue(email.from_email.startswith('Bright Smiles Dental <'))
        self.assertIn(f'{day:%B} {day.day}, {day.year}', email.body)
        self.assertNotIn(f'{day:%B} 0', email.body)
        self.assertIn('call us at (555) 010-4567', email.body)
        self.assertIn('123 Main St', email.body)

    def test_recall_names_the_office(self):
        Appointment.objects.create(patient=self.patient, date=timezone_today_plus(-400), start_time=datetime.time(9, 0),
                                   appointment_type='cleaning', status='completed')
        call_command('send_recall_reminders', stdout=io.StringIO())
        email = mail.outbox[0]
        self.assertIn('Bright Smiles Dental', email.subject)
        self.assertIn('(555) 010-4567', email.body)
