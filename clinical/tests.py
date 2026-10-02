import datetime

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from patients.models import Patient
from staff.models import StaffProfile, TOTPDevice
from .models import ToothCondition, TreatmentPlan, TreatmentPlanItem, TreatmentRecord
from .teeth import build_chart, parse_teeth, tooth_info


def make_staff(username, role):
    user = User.objects.create_user(username=username, password='testpass123')
    StaffProfile.objects.create(user=user, role=role)
    TOTPDevice.objects.create(user=user, secret='JBSWY3DPEHPK3PXP', confirmed=True)
    return user


class ToothHelperTests(TestCase):
    def test_parse_teeth_handles_common_formats(self):
        self.assertEqual(parse_teeth('14'), {14})
        self.assertEqual(parse_teeth('#3, #4'), {3, 4})
        self.assertEqual(parse_teeth('18-20'), {18, 19, 20})
        self.assertEqual(parse_teeth('UR quadrant'), set())
        self.assertEqual(parse_teeth('0, 33, 99'), set())
        self.assertEqual(parse_teeth(''), set())

    def test_tooth_names_follow_universal_numbering(self):
        self.assertEqual(tooth_info(1), ('molar', 'Upper right third molar'))
        self.assertEqual(tooth_info(8), ('incisor', 'Upper right central incisor'))
        self.assertEqual(tooth_info(14), ('molar', 'Upper left first molar'))
        self.assertEqual(tooth_info(17), ('molar', 'Lower left third molar'))
        self.assertEqual(tooth_info(27), ('canine', 'Lower right canine'))
        self.assertEqual(tooth_info(32), ('molar', 'Lower right third molar'))


class ToothChartTests(TestCase):
    def setUp(self):
        self.patient = Patient.objects.create(
            first_name='Chart', last_name='Patient',
            date_of_birth=datetime.date(1990, 1, 1), phone='555-0000',
        )
        self.dentist = make_staff('drchart', 'dentist')
        self.receptionist = make_staff('frontdesk', 'receptionist')

    def test_chart_collects_conditions_history_and_planned_work(self):
        ToothCondition.objects.create(patient=self.patient, tooth_number=3, condition='crown')
        TreatmentRecord.objects.create(
            patient=self.patient, date=datetime.date(2026, 1, 5), procedure='Filling', tooth_number='#14, #15',
        )
        plan = TreatmentPlan.objects.create(patient=self.patient, title='Plan A')
        TreatmentPlanItem.objects.create(plan=plan, procedure='Crown', tooth_number='19')
        TreatmentPlanItem.objects.create(plan=plan, procedure='Done', tooth_number='20', status='completed')

        chart = build_chart(self.patient)
        teeth = {t['number']: t for t in chart['all']}
        self.assertEqual(len(teeth), 32)
        self.assertEqual(teeth[3]['code'], 'crown')
        self.assertEqual(teeth[4]['code'], 'healthy')
        self.assertEqual(len(teeth[14]['records']), 1)
        self.assertEqual(len(teeth[15]['records']), 1)
        self.assertEqual([i.procedure for i in teeth[19]['planned']], ['Crown'])
        self.assertEqual(teeth[20]['planned'], [])
        # Rows line up: tooth 32 sits directly under tooth 1.
        self.assertEqual(teeth[1]['x'], teeth[32]['x'])

    def test_dentist_can_set_and_clear_a_condition(self):
        self.client.force_login(self.dentist)
        url = reverse('tooth_update', args=[self.patient.pk, 14])
        response = self.client.post(url, {'condition': 'filling', 'notes': 'MOD'})
        self.assertRedirects(response, reverse('tooth_chart', args=[self.patient.pk]) + '?tooth=14')
        cond = ToothCondition.objects.get(patient=self.patient, tooth_number=14)
        self.assertEqual((cond.condition, cond.notes, cond.updated_by), ('filling', 'MOD', self.dentist))

        self.client.post(url, {'condition': 'crown', 'notes': ''})
        self.assertEqual(ToothCondition.objects.get(patient=self.patient, tooth_number=14).condition, 'crown')
        self.assertEqual(ToothCondition.objects.count(), 1)

        self.client.post(url, {'condition': 'healthy'})
        self.assertFalse(ToothCondition.objects.exists())

    def test_invalid_input_is_rejected(self):
        self.client.force_login(self.dentist)
        self.client.post(reverse('tooth_update', args=[self.patient.pk, 14]), {'condition': 'bogus'})
        self.client.post(reverse('tooth_update', args=[self.patient.pk, 40]), {'condition': 'crown'})
        self.assertFalse(ToothCondition.objects.exists())

    def test_receptionist_can_view_but_not_edit(self):
        self.client.force_login(self.receptionist)
        response = self.client.get(reverse('tooth_chart', args=[self.patient.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Update condition')
        self.client.post(reverse('tooth_update', args=[self.patient.pk, 14]), {'condition': 'crown'})
        self.assertFalse(ToothCondition.objects.exists())

    def test_patient_account_is_blocked(self):
        user = User.objects.create_user(username='pt', password='testpass123')
        user.groups.add(Group.objects.get_or_create(name='Patient')[0])
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('tooth_chart', args=[self.patient.pk])).status_code, 302)
        self.client.post(reverse('tooth_update', args=[self.patient.pk, 14]), {'condition': 'crown'})
        self.assertFalse(ToothCondition.objects.exists())

    def test_pages_render_with_chart(self):
        ToothCondition.objects.create(patient=self.patient, tooth_number=30, condition='missing')
        self.client.force_login(self.dentist)
        response = self.client.get(reverse('tooth_chart', args=[self.patient.pk]), {'tooth': '30'})
        self.assertContains(response, 'Lower right first molar')
        self.assertContains(response, 'Update condition')
        for bad in ('abc', '99'):
            self.assertEqual(self.client.get(reverse('tooth_chart', args=[self.patient.pk]), {'tooth': bad}).status_code, 200)
        self.assertContains(self.client.get(reverse('patient_detail', args=[self.patient.pk])), 'class="tooth-chart"')


class TreatmentPlanEditingTests(TestCase):
    """Regression guard: adding plan items used to fail silently because the
    form required a status field the page never showed."""

    def setUp(self):
        self.patient = Patient.objects.create(first_name='Plan', last_name='Patient',
                                              date_of_birth=datetime.date(1990, 1, 1), phone='555-0000')
        self.plan = TreatmentPlan.objects.create(patient=self.patient, title='Restore #14')
        self.dentist = make_staff('drplan', 'dentist')
        self.receptionist = make_staff('deskplan', 'receptionist')
        self.url = reverse('plan_detail', args=[self.plan.pk])

    def test_dentist_can_add_an_item_with_just_procedure_tooth_and_cost(self):
        self.client.force_login(self.dentist)
        response = self.client.post(self.url, {'procedure': 'Crown', 'tooth_number': '14', 'estimated_cost': '1500'})
        self.assertRedirects(response, self.url)
        item = self.plan.items.get()
        self.assertEqual((item.procedure, item.tooth_number, item.status), ('Crown', '14', 'pending'))

    def test_invalid_item_shows_why(self):
        self.client.force_login(self.dentist)
        response = self.client.post(self.url, {'procedure': '', 'estimated_cost': 'abc'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'This field is required.')
        self.assertContains(response, 'Enter a number.')
        self.assertFalse(self.plan.items.exists())

    def test_non_dentists_can_view_but_not_change_plans(self):
        self.client.force_login(self.receptionist)
        page = self.client.get(self.url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Only a dentist can change this treatment plan.')
        self.assertNotContains(page, 'Edit Plan')
        self.client.post(self.url, {'procedure': 'Crown', 'estimated_cost': '1'})
        self.assertFalse(self.plan.items.exists())

    def test_dentist_can_change_plan_status_but_not_its_patient(self):
        other = Patient.objects.create(first_name='Other', last_name='Person',
                                       date_of_birth=datetime.date(1990, 1, 1), phone='555-1111')
        self.client.force_login(self.dentist)
        response = self.client.post(reverse('plan_edit', args=[self.plan.pk]), {
            'title': 'Restore #14 and #15', 'status': 'accepted', 'notes': 'Patient agreed.', 'patient': other.pk,
        })
        self.assertRedirects(response, self.url)
        self.plan.refresh_from_db()
        self.assertEqual((self.plan.title, self.plan.status, self.plan.patient), ('Restore #14 and #15', 'accepted', self.patient))

    def test_items_can_be_edited_completed_and_removed(self):
        item = TreatmentPlanItem.objects.create(plan=self.plan, procedure='Crown', tooth_number='14', estimated_cost=1500)
        self.client.force_login(self.dentist)
        self.client.post(reverse('plan_item_edit', args=[item.pk]),
                         {'procedure': 'Crown, porcelain', 'tooth_number': '14', 'estimated_cost': '1450', 'status': 'pending'})
        item.refresh_from_db()
        self.assertEqual((item.procedure, str(item.estimated_cost)), ('Crown, porcelain', '1450.00'))

        # Completing an item is a button (POST) now, not a link anyone could visit.
        self.assertEqual(self.client.get(reverse('plan_item_toggle', args=[item.pk])).status_code, 405)
        self.client.post(reverse('plan_item_toggle', args=[item.pk]))
        item.refresh_from_db()
        self.assertEqual(item.status, 'completed')

        self.client.post(reverse('plan_item_delete', args=[item.pk]))
        self.assertFalse(TreatmentPlanItem.objects.filter(pk=item.pk).exists())

    def test_receptionist_cannot_edit_or_remove_items(self):
        item = TreatmentPlanItem.objects.create(plan=self.plan, procedure='Crown', estimated_cost=1500)
        self.client.force_login(self.receptionist)
        self.client.post(reverse('plan_item_delete', args=[item.pk]))
        self.client.post(reverse('plan_item_edit', args=[item.pk]), {'procedure': 'X', 'estimated_cost': '1', 'status': 'completed'})
        item.refresh_from_db()
        self.assertEqual(item.procedure, 'Crown')


class ProviderChoiceTests(TestCase):
    def setUp(self):
        self.patient = Patient.objects.create(first_name='Pro', last_name='Vider',
                                              date_of_birth=datetime.date(1990, 1, 1), phone='555-0000')
        self.dentist = make_staff('drnames', 'dentist')
        self.dentist.first_name, self.dentist.last_name = 'Elena', 'Park'
        self.dentist.save()
        self.hygienist = make_staff('hygnames', 'hygienist')
        self.hygienist.first_name, self.hygienist.last_name = 'Marcus', 'Reed'
        self.hygienist.save()
        self.patient_user = User.objects.create_user('portaluser', password='x')

    def test_clinical_note_lists_providers_by_name_only(self):
        self.client.force_login(self.dentist)
        page = self.client.get(reverse('record_add', args=[self.patient.pk]))
        self.assertContains(page, 'Dr. Elena Park (Dentist)')
        self.assertContains(page, 'Marcus Reed (Hygienist)')
        self.assertNotContains(page, '>portaluser<')
        # Defaults to whoever is writing the note.
        self.assertContains(page, f'<option value="{self.dentist.pk}" selected>', html=False)

    def test_older_record_with_a_non_provider_still_saves(self):
        record = TreatmentRecord.objects.create(patient=self.patient, dentist=self.patient_user,
                                                date=datetime.date(2026, 1, 5), procedure='Exam')
        self.client.force_login(self.dentist)
        response = self.client.post(reverse('record_edit', args=[record.pk]), {
            'patient': self.patient.pk, 'dentist': self.patient_user.pk, 'date': '2026-01-05',
            'procedure': 'Exam', 'tooth_number': '', 'notes': 'Edited',
        })
        self.assertRedirects(response, reverse('record_detail', args=[record.pk]))


class ClinicalNoteReadingTests(TestCase):
    """From the live-site test: notes could only be read by opening the Edit
    form, which invites accidental changes."""

    def setUp(self):
        self.patient = Patient.objects.create(first_name='Read', last_name='Notes', phone='555-0000',
                                              date_of_birth=datetime.date(1990, 1, 1))
        self.record = TreatmentRecord.objects.create(patient=self.patient, date=datetime.date(2026, 9, 1),
                                                     procedure='Adult cleaning', notes='Light calculus, good home care.')

    def test_hygienist_reads_notes_without_the_edit_form(self):
        self.client.force_login(make_staff('hygread', 'hygienist'))
        detail = self.client.get(reverse('patient_detail', args=[self.patient.pk]))
        self.assertContains(detail, reverse('record_detail', args=[self.record.pk]))
        self.assertContains(detail, reverse('record_add', args=[self.patient.pk]))
        page = self.client.get(reverse('record_detail', args=[self.record.pk]))
        self.assertContains(page, 'Light calculus, good home care.')
        self.assertNotContains(page, '<textarea')

    def test_front_desk_is_told_why_not(self):
        self.client.force_login(make_staff('deskread', 'receptionist'))
        response = self.client.get(reverse('record_detail', args=[self.record.pk]), follow=True)
        self.assertContains(response, 'Only dentists and hygienists can open that page.')
        self.assertNotContains(response, 'Light calculus')

    def test_record_form_checks_tooth_numbers_and_lists_only_this_patients_visits(self):
        from appointments.models import Appointment
        other = Patient.objects.create(first_name='Other', last_name='Person', phone='555-0001',
                                       date_of_birth=datetime.date(1980, 1, 1))
        mine = Appointment.objects.create(patient=self.patient, date=datetime.date(2026, 9, 1), start_time=datetime.time(9, 0))
        theirs = Appointment.objects.create(patient=other, date=datetime.date(2026, 9, 1), start_time=datetime.time(10, 0))
        dentist = make_staff('drread', 'dentist')
        self.client.force_login(dentist)
        page = self.client.get(reverse('record_add', args=[self.patient.pk]))
        self.assertContains(page, f'<option value="{mine.pk}"')
        self.assertNotContains(page, f'<option value="{theirs.pk}"')
        response = self.client.post(reverse('record_add', args=[self.patient.pk]), {
            'patient': self.patient.pk, 'dentist': dentist.pk, 'date': '2026-09-01', 'procedure': 'Filling',
            'tooth_number': '999', 'notes': ''})
        self.assertContains(response, 'isn&#x27;t a tooth number')
        self.assertEqual(TreatmentRecord.objects.count(), 1)
