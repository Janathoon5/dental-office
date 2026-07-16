import datetime
import io
import shutil
import tempfile
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from patients.models import Patient
from staff.models import StaffProfile, TOTPDevice

from .models import DentalImage


def _make_png(name='test.png'):
    buf = io.BytesIO()
    Image.new('RGB', (10, 10)).save(buf, format='PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


class MediaTestCase(TestCase):
    """Overrides MEDIA_ROOT to an isolated temp directory for the class, so
    file-upload tests never write into the project's real media/ directory
    (settings.py forces FileSystemStorage under the test runner regardless of
    .env contents — see the _USE_S3 guard)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()


class ImagingAccessControlTests(MediaTestCase):
    """Regression guard for the cross-patient IDOR bug: these views must be
    staff-only, since patient portal accounts are also plain authenticated
    Users and must not be able to browse other patients' images."""

    def setUp(self):
        self.other_patient = Patient.objects.create(
            first_name='Other', last_name='Patient',
            date_of_birth=datetime.date(1990, 1, 1), phone='555-0000',
        )
        self.image = DentalImage.objects.create(
            patient=self.other_patient, image_type='xray',
            image=_make_png(), captured_date=datetime.date(2026, 1, 1),
        )

        self.patient_user = User.objects.create_user(username='patientuser', password='testpass123')
        patient_group, _ = Group.objects.get_or_create(name='Patient')
        self.patient_user.groups.add(patient_group)
        Patient.objects.create(
            first_name='Self', last_name='Patient',
            date_of_birth=datetime.date(1991, 2, 2), phone='555-1111',
            user=self.patient_user,
        )

        self.staff_user = User.objects.create_user(username='staffuser', password='testpass123')
        StaffProfile.objects.create(user=self.staff_user, role='dentist')
        TOTPDevice.objects.create(user=self.staff_user, secret='JBSWY3DPEHPK3PXP', confirmed=True)

    def _urls(self):
        return [
            reverse('staff_image_list', args=[self.other_patient.pk]),
            reverse('staff_image_upload', args=[self.other_patient.pk]),
            reverse('staff_image_detail', args=[self.image.pk]),
            reverse('staff_image_delete', args=[self.image.pk]),
        ]

    def test_patient_account_is_blocked_from_every_staff_view(self):
        self.client.force_login(self.patient_user)
        for url in self._urls():
            response = self.client.get(url)
            self.assertEqual(
                response.status_code, 302,
                f'{url} should redirect a patient-role account, got {response.status_code}',
            )

    def test_staff_account_can_reach_get_views(self):
        self.client.force_login(self.staff_user)
        for url in (reverse('staff_image_list', args=[self.other_patient.pk]),
                    reverse('staff_image_detail', args=[self.image.pk])):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, f'{url} should be reachable by staff')

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse('staff_image_list', args=[self.other_patient.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)


class StaffImageUploadTests(MediaTestCase):
    def setUp(self):
        self.patient = Patient.objects.create(
            first_name='Api', last_name='Test',
            date_of_birth=datetime.date(1990, 1, 1), phone='555-0000',
        )
        self.staff_user = User.objects.create_user(username='staffuser2', password='testpass123')
        StaffProfile.objects.create(user=self.staff_user, role='dentist')
        TOTPDevice.objects.create(user=self.staff_user, secret='JBSWY3DPEHPK3PXP', confirmed=True)
        self.client.force_login(self.staff_user)

    def test_staff_upload_creates_dental_image(self):
        response = self.client.post(
            reverse('staff_image_upload', args=[self.patient.pk]),
            {'image_type': 'xray', 'image': _make_png(), 'captured_date': '2026-01-01', 'tooth_number': '14'},
        )
        self.assertEqual(response.status_code, 302)

        image = DentalImage.objects.get(patient=self.patient)
        self.assertEqual(image.uploaded_by, self.staff_user)
        self.assertFalse(image.uploaded_by_patient)
        self.assertEqual(image.image_type, 'xray')
        self.assertEqual(image.tooth_number, '14')


class PatientImageUploadTests(MediaTestCase):
    def setUp(self):
        self.patient_user = User.objects.create_user(username='patientuser2', password='testpass123')
        patient_group, _ = Group.objects.get_or_create(name='Patient')
        self.patient_user.groups.add(patient_group)
        self.patient = Patient.objects.create(
            first_name='Self', last_name='Patient',
            date_of_birth=datetime.date(1991, 2, 2), phone='555-1111',
            user=self.patient_user,
        )
        self.client.force_login(self.patient_user)

    def test_patient_upload_is_pinned_to_photo_and_flagged(self):
        response = self.client.post(
            reverse('patient_images'),
            {'image': _make_png(), 'captured_date': '2026-01-01'},
        )
        self.assertEqual(response.status_code, 302)

        image = DentalImage.objects.get(patient=self.patient)
        self.assertEqual(image.image_type, 'photo')
        self.assertTrue(image.uploaded_by_patient)
        self.assertEqual(image.uploaded_by, self.patient_user)

    def test_another_patients_images_are_not_visible(self):
        other_patient = Patient.objects.create(
            first_name='Other', last_name='Patient',
            date_of_birth=datetime.date(1990, 1, 1), phone='555-0000',
        )
        DentalImage.objects.create(
            patient=other_patient, image_type='photo',
            image=_make_png(), captured_date=datetime.date(2026, 1, 1),
        )
        response = self.client.get(reverse('patient_images'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['images']), [])


class ImageValidationTests(MediaTestCase):
    def setUp(self):
        self.patient = Patient.objects.create(
            first_name='Val', last_name='Test',
            date_of_birth=datetime.date(1990, 1, 1), phone='555-0000',
        )
        self.staff_user = User.objects.create_user(username='staffuser3', password='testpass123')
        StaffProfile.objects.create(user=self.staff_user, role='dentist')
        TOTPDevice.objects.create(user=self.staff_user, secret='JBSWY3DPEHPK3PXP', confirmed=True)
        self.client.force_login(self.staff_user)

    def test_disallowed_extension_is_rejected(self):
        fake = SimpleUploadedFile('test.txt', b'not an image', content_type='text/plain')
        self.client.post(
            reverse('staff_image_upload', args=[self.patient.pk]),
            {'image_type': 'xray', 'image': fake, 'captured_date': '2026-01-01'},
        )
        self.assertFalse(DentalImage.objects.filter(patient=self.patient).exists())

    def test_renamed_non_image_file_is_rejected(self):
        """Extension whitelist alone can't catch this — the Pillow
        content-sniff in validate_dental_image is what rejects it."""
        fake = SimpleUploadedFile('test.jpg', b'not actually an image', content_type='image/jpeg')
        self.client.post(
            reverse('staff_image_upload', args=[self.patient.pk]),
            {'image_type': 'xray', 'image': fake, 'captured_date': '2026-01-01'},
        )
        self.assertFalse(DentalImage.objects.filter(patient=self.patient).exists())

    def test_oversized_image_is_rejected(self):
        with patch('imaging.validators.MAX_IMAGE_UPLOAD_MB', 0):
            self.client.post(
                reverse('staff_image_upload', args=[self.patient.pk]),
                {'image_type': 'xray', 'image': _make_png(), 'captured_date': '2026-01-01'},
            )
        self.assertFalse(DentalImage.objects.filter(patient=self.patient).exists())


class AuditlogTests(MediaTestCase):
    def test_staff_upload_creates_audit_log_entry(self):
        from auditlog.models import LogEntry

        patient = Patient.objects.create(
            first_name='Audit', last_name='Test',
            date_of_birth=datetime.date(1990, 1, 1), phone='555-0000',
        )
        staff_user = User.objects.create_user(username='staffuser4', password='testpass123')
        StaffProfile.objects.create(user=staff_user, role='dentist')
        TOTPDevice.objects.create(user=staff_user, secret='JBSWY3DPEHPK3PXP', confirmed=True)
        self.client.force_login(staff_user)

        self.client.post(
            reverse('staff_image_upload', args=[patient.pk]),
            {'image_type': 'xray', 'image': _make_png(), 'captured_date': '2026-01-01'},
        )

        self.assertTrue(LogEntry.objects.filter(content_type__model='dentalimage').exists())
