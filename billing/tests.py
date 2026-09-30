import datetime
import io
import json
import shutil
import tempfile
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from clinical.models import ToothCondition, TreatmentRecord
from patients.models import MedicalAlert, Patient
from staff.models import StaffProfile, TOTPDevice
from .models import ClaimDenial, Invoice, InvoiceLineItem, OfficeSettings


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
        TOTPDevice.objects.create(user=self.staff_user, secret='JBSWY3DPEHPK3PXP', confirmed=True)

    def _get_urls(self):
        return [
            reverse('invoice_list'),
            reverse('invoice_add'),
            reverse('invoice_detail', args=[self.invoice.pk]),
            reverse('invoice_edit', args=[self.invoice.pk]),
            reverse('payment_add', args=[self.invoice.pk]),
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
        for url in (reverse('invoice_list'), reverse('invoice_add'),
                    reverse('invoice_detail', args=[self.invoice.pk]),
                    reverse('invoice_edit', args=[self.invoice.pk])):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, f'{url} should be reachable by staff')


AI_RESULT = {
    'insurer_name': 'Delta Test Dental',
    'claim_number': 'CLM-123',
    'denial_codes': 'N30, 96',
    'amount_denied': '$1,150.00',
    'appeal_deadline': '2026-12-01',
    'summary': 'The crown on #14 was denied as not medically necessary.',
    'denial_reason': 'Insufficient documentation of necessity.',
    'recommendation': 'appeal',
    'recommendation_reason': 'Records show a fractured cusp.',
    'checklist': [{'item': 'Pre-op X-ray of #14', 'why': 'Shows the fracture', 'on_file': True}],
    'warnings': ['Member ID on the letter differs from the chart.'],
    'letter': 'Dear Claims Reviewer,\n[DENTIST TO CONFIRM: fracture size]\nSincerely,',
}


def fake_response(payload=AI_RESULT, stop_reason='end_turn', content=None):
    if content is None:
        content = [SimpleNamespace(type='text', text=json.dumps(payload))]
    return SimpleNamespace(stop_reason=stop_reason, content=content)


def mock_claude(response):
    """Patch the Anthropic client so .beta.messages.stream(...) returns `response`.
    The returned mock records the kwargs the app sent."""
    client = mock.MagicMock()
    stream_cm = client.beta.messages.stream.return_value
    stream_cm.__enter__.return_value.get_final_message.return_value = response
    return mock.patch('billing.ai.anthropic.Anthropic', return_value=client), client


class ClaimDenialTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        media_override = override_settings(MEDIA_ROOT=self.media, ANTHROPIC_API_KEY='test-key', AI_PHI_ALLOWED=False)
        media_override.enable()
        self.addCleanup(media_override.disable)

        self.patient = Patient.objects.create(
            first_name='Test', last_name='Patient', date_of_birth=datetime.date(1980, 5, 5),
            phone='555-0000', insurance_provider='Delta Test Dental', insurance_id='M-999',
        )
        self.invoice = Invoice.objects.create(patient=self.patient, subtotal=1500, insurance_amount=1150)
        self.staff = User.objects.create_user(username='frontdesk', password='testpass123')
        StaffProfile.objects.create(user=self.staff, role='receptionist')
        TOTPDevice.objects.create(user=self.staff, secret='JBSWY3DPEHPK3PXP', confirmed=True)
        self.client.force_login(self.staff)

    def _upload(self, name='letter.pdf', content=b'%PDF-1.4 fake', confirm=True, **extra):
        data = {'letter': SimpleUploadedFile(name, content)}
        if confirm:
            data['confirm_no_phi'] = 'on'
        return self.client.post(reverse('denial_upload', args=[self.invoice.pk]), data, **extra)

    def test_demo_mode_requires_no_phi_confirmation(self):
        patcher, _ = mock_claude(fake_response())
        with patcher:
            self._upload(confirm=False)
        self.assertFalse(ClaimDenial.objects.exists())

    @override_settings(AI_PHI_ALLOWED=True)
    def test_confirmation_not_needed_once_phi_is_allowed(self):
        patcher, _ = mock_claude(fake_response())
        with patcher:
            self._upload(confirm=False)
        self.assertEqual(ClaimDenial.objects.count(), 1)

    def test_upload_runs_analysis_and_saves_result(self):
        patcher, _ = mock_claude(fake_response())
        with patcher:
            response = self._upload()
        denial = ClaimDenial.objects.get()
        self.assertRedirects(response, reverse('denial_detail', args=[denial.pk]))
        self.assertEqual(denial.ai_status, 'done')
        self.assertEqual(denial.created_by, self.staff)
        self.assertEqual(denial.insurer_name, 'Delta Test Dental')
        self.assertEqual(str(denial.amount_denied), '1150.00')
        self.assertEqual(denial.appeal_deadline, datetime.date(2026, 12, 1))
        self.assertEqual(denial.recommendation, 'appeal')
        self.assertEqual(denial.checklist[0]['on_file'], True)

        page = self.client.get(reverse('denial_detail', args=[denial.pk]))
        self.assertContains(page, 'fractured cusp')
        self.assertContains(page, 'Member ID on the letter differs')
        self.assertContains(page, '1 for the dentist')
        self.assertContains(page, '<mark class="ph ph-dentist">[DENTIST TO CONFIRM: fracture size]</mark>', html=False)
        self.assertContains(page, 'Demo mode')

    def test_request_includes_letter_and_patient_records(self):
        MedicalAlert.objects.create(patient=self.patient, alert_type='condition', description='Type 2 diabetes')
        ToothCondition.objects.create(patient=self.patient, tooth_number=14, condition='decay', notes='fractured cusp')
        TreatmentRecord.objects.create(patient=self.patient, date=datetime.date.today(), procedure='Crown prep', tooth_number='14')
        OfficeSettings.objects.create(pk=1, office_name='Bright Smiles Dental', npi='1234567890')

        patcher, client = mock_claude(fake_response())
        with patcher:
            self._upload()
        kwargs = client.beta.messages.stream.call_args.kwargs
        self.assertEqual(kwargs['model'], 'claude-opus-5-5')
        self.assertEqual(kwargs['fallbacks'], 'default')
        self.assertEqual(kwargs['output_config']['format']['type'], 'json_schema')
        letter_block, text_block = kwargs['messages'][0]['content']
        self.assertEqual(letter_block['type'], 'document')
        self.assertEqual(letter_block['source']['media_type'], 'application/pdf')
        for expected in ('Type 2 diabetes', '#14 Upper left first molar: Decay / Cavity (fractured cusp)',
                         'Crown prep, tooth 14', 'Bright Smiles Dental', '1234567890', 'M-999',
                         'None uploaded to the app.'):
            self.assertIn(expected, text_block['text'])

    def test_photos_are_sent_as_images(self):
        patcher, client = mock_claude(fake_response())
        with patcher:
            self._upload(name='letter.JPG', content=b'\xff\xd8fakejpeg')
        block = client.beta.messages.stream.call_args.kwargs['messages'][0]['content'][0]
        self.assertEqual((block['type'], block['source']['media_type']), ('image', 'image/jpeg'))

    def test_unsupported_file_type_is_rejected(self):
        patcher, client = mock_claude(fake_response())
        with patcher:
            self._upload(name='letter.docx')
        self.assertFalse(ClaimDenial.objects.exists())
        client.beta.messages.stream.assert_not_called()

    @override_settings(ANTHROPIC_API_KEY='')
    def test_missing_api_key_fails_with_setup_instructions(self):
        self._upload()
        denial = ClaimDenial.objects.get()
        self.assertEqual(denial.ai_status, 'failed')
        self.assertIn('ANTHROPIC_API_KEY', denial.ai_error)
        self.assertContains(self.client.get(reverse('denial_detail', args=[denial.pk])), 'Try again')

    def test_refusal_is_reported_not_parsed(self):
        patcher, _ = mock_claude(fake_response(stop_reason='refusal', content=[]))
        with patcher:
            self._upload()
        denial = ClaimDenial.objects.get()
        self.assertEqual(denial.ai_status, 'failed')
        self.assertIn('declined', denial.ai_error)

    def test_only_text_after_a_fallback_switch_is_used(self):
        content = [
            SimpleNamespace(type='text', text='{"partial": '),
            SimpleNamespace(type='fallback'),
            SimpleNamespace(type='text', text=json.dumps(AI_RESULT)),
        ]
        patcher, _ = mock_claude(fake_response(content=content))
        with patcher:
            self._upload()
        self.assertEqual(ClaimDenial.objects.get().ai_status, 'done')

    def test_staff_can_edit_status_deadline_and_letter(self):
        patcher, _ = mock_claude(fake_response())
        with patcher:
            self._upload()
        denial = ClaimDenial.objects.get()
        self.client.post(reverse('denial_detail', args=[denial.pk]), {
            'status': 'appealed', 'appeal_deadline': '2026-11-15', 'appeal_letter': 'Edited letter',
        })
        denial.refresh_from_db()
        self.assertEqual((denial.status, denial.appeal_deadline, denial.appeal_letter),
                         ('appealed', datetime.date(2026, 11, 15), 'Edited letter'))
        self.assertContains(self.client.get(reverse('denial_print', args=[denial.pk])), 'Edited letter')

    def test_retry_reruns_analysis(self):
        with override_settings(ANTHROPIC_API_KEY=''):
            self._upload()
        denial = ClaimDenial.objects.get()
        patcher, _ = mock_claude(fake_response())
        with patcher:
            self.client.post(reverse('denial_retry', args=[denial.pk]))
        denial.refresh_from_db()
        self.assertEqual(denial.ai_status, 'done')

    def test_stuck_analysis_is_detected(self):
        denial = ClaimDenial.objects.create(invoice=self.invoice, letter='denials/x.pdf', ai_status='processing')
        from django.utils import timezone
        denial.ai_started_at = timezone.now() - datetime.timedelta(minutes=11)
        self.assertTrue(denial.ai_is_stuck)
        denial.ai_started_at = timezone.now()
        self.assertFalse(denial.ai_is_stuck)

    def test_list_shows_open_denials_soonest_deadline_first(self):
        later = ClaimDenial.objects.create(invoice=self.invoice, letter='a.pdf', ai_status='done',
                                           insurer_name='Later Ins', appeal_deadline=datetime.date(2027, 1, 1))
        sooner = ClaimDenial.objects.create(invoice=self.invoice, letter='b.pdf', ai_status='done',
                                            insurer_name='Sooner Ins', appeal_deadline=datetime.date(2026, 11, 1))
        ClaimDenial.objects.create(invoice=self.invoice, letter='c.pdf', ai_status='done',
                                   insurer_name='Closed Ins', status='approved')
        response = self.client.get(reverse('denial_list'))
        self.assertEqual([d.pk for d in response.context['denials']], [sooner.pk, later.pk])
        self.assertNotContains(response, 'Closed Ins')
        self.assertContains(self.client.get(reverse('denial_list'), {'show': 'closed'}), 'Closed Ins')

    def test_original_letter_is_served_to_staff_only(self):
        patcher, _ = mock_claude(fake_response())
        with patcher:
            self._upload(content=b'%PDF-1.4 secret')
        denial = ClaimDenial.objects.get()
        response = self.client.get(reverse('denial_letter_file', args=[denial.pk]))
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertEqual(b''.join(response.streaming_content), b'%PDF-1.4 secret')

        patient_user = User.objects.create_user(username='pt', password='testpass123')
        patient_user.groups.add(Group.objects.get_or_create(name='Patient')[0])
        self.client.force_login(patient_user)
        for name in ('denial_detail', 'denial_letter_file', 'denial_print', 'denial_retry'):
            self.assertEqual(self.client.get(reverse(name, args=[denial.pk])).status_code, 302, name)
        self.assertEqual(self.client.get(reverse('denial_list')).status_code, 302)
        self._upload()
        self.assertEqual(ClaimDenial.objects.count(), 1)


class PlaceholderTests(TestCase):
    def test_placeholders_are_sorted_by_who_answers_them(self):
        from .placeholders import find_placeholders
        letter = ('Tooth [DENTIST TO CONFIRM: pocket depths on #3] seated on [STAFF TO VERIFY: seat date]. '
                  'Enclosed: [ATTACH: bitewing X-ray], [ATTACH if available: photo], [DATE OF SERVICE]. '
                  'Again: [DENTIST TO CONFIRM: pocket depths on #3]')
        items = find_placeholders(letter)
        self.assertEqual([(i['category'], i['question']) for i in items], [
            ('dentist', 'pocket depths on #3'),
            ('staff', 'seat date'),
            ('attach', 'bitewing X-ray'),
            ('attach', 'photo'),
            ('staff', 'DATE OF SERVICE'),
        ])

    def test_highlight_escapes_html(self):
        from .placeholders import highlight
        html = highlight('<b>x</b> [STAFF TO VERIFY: <i>id</i>]')
        self.assertEqual(html, '&lt;b&gt;x&lt;/b&gt; <mark class="ph ph-staff">[STAFF TO VERIFY: &lt;i&gt;id&lt;/i&gt;]</mark>')


REVIEW_LETTER = (
    'Dear Reviewer,\n'
    'Tooth #14 had [DENTIST TO CONFIRM: how much tooth structure was lost?] missing.\n'
    'Member ID: [STAFF TO VERIFY: correct member ID]\n'
    'Enclosed:\n1. X-ray\n2. [ATTACH: intraoral photo of #14]\n'
)


class DenialReviewTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        overrides = override_settings(MEDIA_ROOT=self.media, ANTHROPIC_API_KEY='test-key')
        overrides.enable()
        self.addCleanup(overrides.disable)

        patient = Patient.objects.create(first_name='Test', last_name='Patient',
                                         date_of_birth=datetime.date(1980, 5, 5), phone='555-0000')
        invoice = Invoice.objects.create(patient=patient, subtotal=1500, insurance_amount=1150)
        self.denial = ClaimDenial.objects.create(invoice=invoice, letter='x.pdf', ai_status='done',
                                                 appeal_letter=REVIEW_LETTER)
        self.dentist = self._staff('drsmith', 'dentist', 'Jane', 'Smith')
        self.receptionist = self._staff('desk', 'receptionist')
        self.url = reverse('denial_review', args=[self.denial.pk])

    def _staff(self, username, role, first='', last=''):
        user = User.objects.create_user(username=username, password='testpass123', first_name=first, last_name=last)
        StaffProfile.objects.create(user=user, role=role)
        TOTPDevice.objects.create(user=user, secret='JBSWY3DPEHPK3PXP', confirmed=True)
        return user

    def _post(self, **fields):
        data = {
            'ph_0': '[DENTIST TO CONFIRM: how much tooth structure was lost?]',
            'ph_1': '[STAFF TO VERIFY: correct member ID]',
            'ph_2': '[ATTACH: intraoral photo of #14]',
        }
        data.update(fields)
        return self.client.post(self.url, data)

    def test_checklist_groups_items_and_locks_clinical_ones_for_non_dentists(self):
        self.client.force_login(self.receptionist)
        page = self.client.get(self.url)
        self.assertContains(page, 'How much tooth structure was lost?')
        self.assertContains(page, 'Correct member ID')
        self.assertContains(page, 'Intraoral photo of #14')
        self.assertContains(page, 'Only a dentist can answer these')
        self.assertContains(page, 'Waiting for the dentist')

        self.client.force_login(self.dentist)
        self.assertNotContains(self.client.get(self.url), 'Waiting for the dentist')

    def test_dentist_answers_are_sent_to_ai_and_letter_is_updated(self):
        revised = {'letter': 'Dear Reviewer,\nAbout 50% was missing.\n', 'changes': ['Added the tooth structure loss.']}
        patcher, client = mock_claude(fake_response(payload=revised))
        self.client.force_login(self.dentist)
        with patcher:
            response = self._post(answer_0='About 50%', answer_1='SDI-448812', remove_2='on')
        self.assertRedirects(response, reverse('denial_detail', args=[self.denial.pk]))

        self.denial.refresh_from_db()
        self.assertEqual(self.denial.ai_task, 'revise')
        self.assertEqual(self.denial.ai_status, 'done')
        self.assertEqual(self.denial.appeal_letter, revised['letter'])
        self.assertEqual(self.denial.revision_notes, revised['changes'])

        kwargs = client.beta.messages.stream.call_args.kwargs
        self.assertIn('You edit dental insurance appeal', kwargs['system'])
        sent = kwargs['messages'][0]['content'][0]['text']
        self.assertIn(REVIEW_LETTER, sent)
        self.assertIn('Answer: About 50%', sent)
        self.assertIn('Answered by: Jane Smith (dentist)', sent)
        self.assertIn('Answer: SDI-448812', sent)
        self.assertIn('Placeholder: [ATTACH: intraoral photo of #14]', sent)
        self.assertIn('Answer: REMOVE (not available)', sent)

        page = self.client.get(reverse('denial_detail', args=[self.denial.pk]))
        self.assertContains(page, 'Added the tooth structure loss.')
        self.assertContains(page, 'No open items')

    def test_non_dentist_cannot_answer_clinical_items(self):
        patcher, client = mock_claude(fake_response(payload={'letter': 'x', 'changes': []}))
        self.client.force_login(self.receptionist)
        with patcher:
            self._post(answer_0='I made this up', answer_1='SDI-448812', attach_2='on')
        answers = ClaimDenial.objects.get().review_answers
        self.assertEqual([a['category'] for a in answers], ['staff', 'attach'])
        sent = client.beta.messages.stream.call_args.kwargs['messages'][0]['content'][0]['text']
        self.assertNotIn('I made this up', sent)
        self.assertIn('Answer: WILL ATTACH', sent)

    def test_blank_form_does_not_call_ai(self):
        patcher, client = mock_claude(fake_response())
        self.client.force_login(self.dentist)
        with patcher:
            response = self._post()
        self.assertRedirects(response, self.url)
        client.beta.messages.stream.assert_not_called()

    def test_changed_letter_is_detected(self):
        patcher, client = mock_claude(fake_response())
        self.client.force_login(self.dentist)
        with patcher:
            response = self._post(ph_0='[DENTIST TO CONFIRM: something else]', answer_0='x')
        self.assertRedirects(response, self.url)
        client.beta.messages.stream.assert_not_called()

    def test_failed_update_keeps_letter_and_answers_then_retry_revises(self):
        self.client.force_login(self.dentist)
        with override_settings(ANTHROPIC_API_KEY=''):
            self._post(answer_0='About 50%')
        self.denial.refresh_from_db()
        self.assertEqual((self.denial.ai_status, self.denial.appeal_letter), ('failed', REVIEW_LETTER))
        page = self.client.get(reverse('denial_detail', args=[self.denial.pk]))
        self.assertContains(page, 'your review answers are saved')

        patcher, client = mock_claude(fake_response(payload={'letter': 'Fixed', 'changes': ['ok']}))
        with patcher:
            self.client.post(reverse('denial_retry', args=[self.denial.pk]))
        self.denial.refresh_from_db()
        self.assertEqual((self.denial.ai_status, self.denial.appeal_letter), ('done', 'Fixed'))
        sent = client.beta.messages.stream.call_args.kwargs['messages'][0]['content'][0]['text']
        self.assertIn('Answer: About 50%', sent)

    def test_saved_answers_prefill_the_checklist(self):
        self.denial.review_answers = [{
            'placeholder': '[DENTIST TO CONFIRM: how much tooth structure was lost?]', 'category': 'dentist',
            'question': 'q', 'answer': 'About 50%', 'remove': False, 'answered_by': 'Jane Smith',
        }]
        self.denial.save()
        self.client.force_login(self.dentist)
        self.assertContains(self.client.get(self.url), 'About 50%')

    def test_rerun_ai_button_starts_a_fresh_analysis(self):
        self.denial.ai_task = 'revise'
        self.denial.save()
        self.client.force_login(self.dentist)
        with mock.patch('billing.views.start_ai_task') as start:
            self.client.post(reverse('denial_retry', args=[self.denial.pk]), {'task': 'analyze'})
        self.assertEqual(start.call_args.args[1], 'analyze')

    def test_list_shows_open_item_count_and_patients_are_blocked(self):
        self.client.force_login(self.receptionist)
        self.assertContains(self.client.get(reverse('denial_list')), '3 to confirm')
        patient_user = User.objects.create_user(username='pt', password='testpass123')
        patient_user.groups.add(Group.objects.get_or_create(name='Patient')[0])
        self.client.force_login(patient_user)
        self.assertEqual(self.client.get(self.url).status_code, 302)


def make_pdf(text):
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 720, text)
    c.showPage()
    c.save()
    return buf.getvalue()


def make_png(color=(200, 200, 200)):
    from PIL import Image as PILImage
    buf = io.BytesIO()
    PILImage.new('RGB', (300, 200), color).save(buf, 'PNG')
    return buf.getvalue()


def pdf_text(data):
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    return reader, '\n'.join(page.extract_text() for page in reader.pages)


class StaffTestMixin:
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        overrides = override_settings(MEDIA_ROOT=self.media, ANTHROPIC_API_KEY='test-key')
        overrides.enable()
        self.addCleanup(overrides.disable)
        self.patient = Patient.objects.create(
            first_name='Maria', last_name='Lopez', date_of_birth=datetime.date(1985, 3, 2), phone='555-0000',
            insurance_provider='Sunrise Dental', insurance_id='SDI-448812',
        )
        self.invoice = Invoice.objects.create(patient=self.patient, subtotal=0)
        self.staff = User.objects.create_user(username='desk', password='testpass123')
        StaffProfile.objects.create(user=self.staff, role='receptionist')
        TOTPDevice.objects.create(user=self.staff, secret='JBSWY3DPEHPK3PXP', confirmed=True)
        self.client.force_login(self.staff)


class InvoiceLineItemTests(StaffTestMixin, TestCase):
    def _add(self, **overrides):
        data = {'service_date': '2026-08-28', 'cdt_code': 'D2740', 'tooth_number': '14', 'surfaces': '',
                'description': 'Crown, porcelain/ceramic', 'fee': '1500.00'}
        data.update(overrides)
        return self.client.post(reverse('line_item_add', args=[self.invoice.pk]), data)

    def test_adding_and_removing_lines_keeps_subtotal_in_sync(self):
        self._add()
        self._add(cdt_code='d2950', description='Core buildup', fee='250', surfaces='m o')
        self.invoice.refresh_from_db()
        self.assertEqual(str(self.invoice.subtotal), '1750.00')
        buildup = InvoiceLineItem.objects.get(cdt_code='D2950')
        self.assertEqual(buildup.surfaces, 'MO')

        self.client.post(reverse('line_item_delete', args=[buildup.pk]))
        self.invoice.refresh_from_db()
        self.assertEqual(str(self.invoice.subtotal), '1500.00')

        page = self.client.get(reverse('invoice_detail', args=[self.invoice.pk]))
        self.assertContains(page, 'D2740')
        self.assertContains(page, '<option value="D2392">', html=False)
        edit_form = self.client.get(reverse('invoice_edit', args=[self.invoice.pk]))
        self.assertContains(edit_form, 'Calculated from the procedures')

    def test_invalid_code_and_surfaces_are_rejected(self):
        self._add(cdt_code='2740')
        self._add(surfaces='XYZ')
        self.assertFalse(InvoiceLineItem.objects.exists())
        page = self.client.get(reverse('invoice_detail', args=[self.invoice.pk]))
        self.assertContains(page, 'Use a CDT code like D2740.')
        self.assertContains(page, 'Use surface letters')

    def test_ai_sees_the_claim_lines(self):
        from .ai import build_case_context
        self.assertIn('Not itemized on our invoice', build_case_context(self.invoice))
        self._add(surfaces='MOD')
        self.assertIn('- 2026-08-28: D2740 Crown, porcelain/ceramic, tooth 14, surfaces MOD, $1500.00',
                      build_case_context(self.invoice))

    def test_patients_cannot_edit_lines(self):
        patient_user = User.objects.create_user(username='pt', password='testpass123')
        patient_user.groups.add(Group.objects.get_or_create(name='Patient')[0])
        self.client.force_login(patient_user)
        self._add()
        self.assertFalse(InvoiceLineItem.objects.exists())


class AppealPacketTests(StaffTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        from imaging.models import DentalImage
        OfficeSettings.objects.create(pk=1, office_name='Bright Smiles Dental', npi='0000000000')
        InvoiceLineItem.objects.create(invoice=self.invoice, service_date=datetime.date(2026, 8, 28), cdt_code='D2740',
                                       description='Crown, porcelain/ceramic', tooth_number='14', fee=1500)
        self.crown_note = TreatmentRecord.objects.create(patient=self.patient, date=datetime.date(2026, 8, 28),
                                                         procedure='Porcelain crown', tooth_number='14',
                                                         notes='Fractured mesiolingual cusp, 50 percent structure lost.')
        self.other_note = TreatmentRecord.objects.create(patient=self.patient, date=datetime.date(2026, 1, 5),
                                                         procedure='Cleaning', notes='Routine.')
        self.xray = DentalImage.objects.create(patient=self.patient, image_type='xray', tooth_number='14',
                                               captured_date=datetime.date(2026, 8, 14), caption='PA pre-op',
                                               image=SimpleUploadedFile('pa.png', make_png()))
        self.other_xray = DentalImage.objects.create(patient=self.patient, image_type='xray', tooth_number='3',
                                                     captured_date=datetime.date(2026, 1, 5),
                                                     image=SimpleUploadedFile('bw.png', make_png()))
        self.denial = ClaimDenial.objects.create(
            invoice=self.invoice, ai_status='done', claim_number='SDI-26-0918', insurer_name='Sunrise Dental',
            letter=SimpleUploadedFile('eob.pdf', make_pdf('ORIGINAL EOB TEXT')),
            appeal_letter='September 30, 2026\n\nDear Reviewer,\nPlease reconsider the crown on #14.\n\nSincerely,\nDr. Smith',
            checklist=[{'item': 'Pre-op X-ray', 'why': 'x', 'on_file': True}],
        )
        self.url = reverse('denial_packet', args=[self.denial.pk])

    def test_options_preselect_items_for_the_denied_tooth(self):
        page = self.client.get(self.url)
        self.assertContains(page, f'value="{self.crown_note.pk}" id="rec{self.crown_note.pk}" checked', html=False)
        self.assertContains(page, f'value="{self.other_note.pk}" id="rec{self.other_note.pk}" >', html=False)
        self.assertContains(page, f'value="{self.xray.pk}" id="img{self.xray.pk}" checked', html=False)
        self.assertContains(page, f'value="{self.other_xray.pk}" id="img{self.other_xray.pk}" >', html=False)

    def test_packet_pdf_contains_every_selected_part(self):
        response = self.client.post(self.url, {
            'summary': 'on', 'original': 'on',
            'records': [self.crown_note.pk], 'images': [self.xray.pk],
        })
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('Appeal packet - Lopez - SDI-26-0918.pdf', response['Content-Disposition'])
        reader, text = pdf_text(response.content)
        # letter, summary, notes, X-ray, original EOB
        self.assertEqual(len(reader.pages), 5)
        for expected in ('Bright Smiles Dental', 'Please reconsider the crown on #14', 'Claim Summary',
                         'SDI-448812', 'D2740', 'Fractured mesiolingual cusp', 'PA pre-op',
                         'Maria Lopez · DOB 03/02/1985 · Claim SDI-26-0918', 'ORIGINAL EOB TEXT'):
            self.assertIn(expected, text)
        self.assertNotIn('Routine.', text)

    def test_letter_only_packet(self):
        response = self.client.post(self.url, {})
        reader, text = pdf_text(response.content)
        self.assertEqual(len(reader.pages), 1)
        self.assertNotIn('ORIGINAL EOB TEXT', text)

    def test_photo_of_insurer_letter_becomes_a_page(self):
        self.denial.letter = SimpleUploadedFile('eob.png', make_png((255, 255, 255)))
        self.denial.save()
        reader, text = pdf_text(self.client.post(self.url, {'original': 'on'}).content)
        self.assertEqual(len(reader.pages), 2)
        self.assertIn("Copy of Insurer's Letter", text)

    def test_unreadable_original_is_noted_instead_of_crashing(self):
        self.denial.letter = SimpleUploadedFile('eob.pdf', b'not really a pdf')
        self.denial.save()
        reader, text = pdf_text(self.client.post(self.url, {'original': 'on'}).content)
        self.assertIn('could not be added', text)

    def test_open_items_warning_and_access(self):
        self.denial.appeal_letter += '\n[DENTIST TO CONFIRM: cusp?]'
        self.denial.save()
        self.assertContains(self.client.get(self.url), 'unanswered [BRACKETED] item')
        patient_user = User.objects.create_user(username='pt', password='testpass123')
        patient_user.groups.add(Group.objects.get_or_create(name='Patient')[0])
        self.client.force_login(patient_user)
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertEqual(self.client.post(self.url, {}).status_code, 302)


class LetterLayoutTests(TestCase):
    def test_signature_gap_after_closing_whether_or_not_letter_leaves_blank_lines(self):
        from types import SimpleNamespace
        from reportlab.platypus import Paragraph, Spacer
        from .packet import _letter_section
        office = SimpleNamespace(office_name='X', address='', phone='', email='', npi='', tax_id='')
        for letter in ('Body.\n\nSincerely,\nDr. Smith', 'Body.\n\nSincerely,\n\n\n\nDr. Smith'):
            story = _letter_section(SimpleNamespace(appeal_letter=letter), office)
            texts = [(type(f).__name__, getattr(f, 'text', '')) for f in story]
            i = texts.index(('Paragraph', 'Sincerely,'))
            self.assertIsInstance(story[i + 1], Spacer)
            self.assertGreaterEqual(story[i + 1].height, 30)
            self.assertEqual(texts[i + 2], ('Paragraph', 'Dr. Smith'))
