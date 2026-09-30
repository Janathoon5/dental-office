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
