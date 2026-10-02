import datetime
import json
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from django.conf import settings

from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from encrypted_model_fields.fields import EncryptedTextField
from dental_office.mixins import SoftDeleteModel
from patients.models import Patient
from appointments.models import Appointment


class Invoice(SoftDeleteModel):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
    ]

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='invoices')
    appointment = models.OneToOneField(Appointment, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoice')
    date_issued = models.DateField(auto_now_add=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    insurance_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ['-date_issued']

    def __str__(self):
        return f"Invoice #{self.pk} — {self.patient} ({self.date_issued})"

    def patient_owes(self):
        return self.subtotal - self.insurance_amount

    def amount_paid(self):
        return sum(p.amount for p in self.payments.all())

    def balance_due(self):
        return self.patient_owes() - self.amount_paid()

    def credit(self):
        """Amount paid beyond what the patient owes, kept as a credit."""
        return max(-self.balance_due(), Decimal('0'))

    def update_status(self):
        """Paid, partly paid or pending, from the payments that still count."""
        if self.balance_due() <= 0:
            self.status = 'paid'
        elif self.amount_paid() > 0:
            self.status = 'partial'
        else:
            self.status = 'pending'
        self.save(update_fields=['status'])

    def voided_payments(self):
        return Payment.all_objects.filter(invoice=self, is_active=False).select_related('deleted_by')

    def recalculate_subtotal(self):
        """Once an invoice has procedure lines, its subtotal is their total."""
        lines = list(self.line_items.all())
        if lines:
            self.subtotal = sum((line.fee for line in lines), Decimal('0'))
            self.save(update_fields=['subtotal'])


class InvoiceLineItem(models.Model):
    """One billed procedure, the way it appears on an insurance claim."""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='line_items')
    service_date = models.DateField('Date of service')
    cdt_code = models.CharField(
        'Procedure code', max_length=5,
        validators=[RegexValidator(r'^D\d{4}$', 'Use a CDT code like D2740.')],
    )
    description = models.CharField(max_length=200)
    tooth_number = models.CharField('Tooth', max_length=20, blank=True)
    surfaces = models.CharField(max_length=10, blank=True)
    fee = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0'))])

    class Meta:
        ordering = ['service_date', 'pk']

    def __str__(self):
        tooth = f' #{self.tooth_number}' if self.tooth_number else ''
        return f'{self.cdt_code}{tooth} {self.description}'


class Payment(SoftDeleteModel):
    METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('card', 'Credit/Debit Card'),
        ('check', 'Check'),
        ('insurance', 'Insurance'),
    ]

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    date = models.DateField(auto_now_add=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='card')
    notes = models.CharField(max_length=200, blank=True)
    # A voided payment is soft-deleted (deleted_by/deleted_at say who and
    # when) and stops counting toward the invoice; this says why.
    void_reason = models.CharField(max_length=200, blank=True)

    class Meta(SoftDeleteModel.Meta):
        pass

    def __str__(self):
        return f"${self.amount} on Invoice #{self.invoice.pk}"


class OfficeSettings(models.Model):
    """Single-row table holding the office letterhead, used on insurance
    appeal letters. Edit it in the admin panel; use OfficeSettings.load()."""
    office_name = models.CharField(max_length=200, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    dentist_name = models.CharField('Treating dentist name', max_length=200, blank=True)
    npi = models.CharField('NPI number', max_length=20, blank=True)
    tax_id = models.CharField('Tax ID (TIN)', max_length=20, blank=True)

    class Meta:
        verbose_name = 'Office settings'
        verbose_name_plural = 'Office settings'

    def __str__(self):
        return self.office_name or 'Office settings'

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


def denial_letter_upload_path(instance, filename):
    ext = Path(filename).suffix.lower()
    return f'denials/{instance.invoice.patient_id}/{uuid4().hex}{ext}'


class ClaimDenial(SoftDeleteModel):
    """An insurance denial letter for an invoice, plus Claude's analysis of it
    and the office's progress on getting it paid."""
    STATUS_CHOICES = [
        ('denied', 'Denied — needs action'),
        ('resubmitted', 'Corrected & resubmitted'),
        ('appealed', 'Appeal sent'),
        ('approved', 'Approved / paid'),
        ('closed', 'Closed — not pursuing'),
    ]
    OPEN_STATUSES = ('denied', 'resubmitted', 'appealed')
    AI_STATUS_CHOICES = [
        ('processing', 'Processing'),
        ('done', 'Done'),
        ('failed', 'Failed'),
    ]
    AI_TASK_CHOICES = [
        ('analyze', 'Analyze letter'),
        ('revise', 'Update letter with review answers'),
    ]
    RECOMMENDATION_CHOICES = [
        ('appeal', 'Appeal'),
        ('resubmit', 'Correct & resubmit'),
        ('not_worth_pursuing', 'Not worth pursuing'),
    ]

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='denials')
    letter = models.FileField(upload_to=denial_letter_upload_path)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='denied')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+',
    )

    # Filled in by the AI analysis (billing/ai.py)
    ai_status = models.CharField(max_length=20, choices=AI_STATUS_CHOICES, default='processing')
    ai_task = models.CharField(max_length=10, choices=AI_TASK_CHOICES, default='analyze')
    ai_error = models.TextField(blank=True)
    ai_started_at = models.DateTimeField(null=True, blank=True)
    insurer_name = models.CharField(max_length=200, blank=True)
    claim_number = models.CharField(max_length=100, blank=True)
    denial_codes = models.CharField(max_length=200, blank=True)
    amount_denied = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    appeal_deadline = models.DateField(null=True, blank=True)
    recommendation = models.CharField(max_length=30, choices=RECOMMENDATION_CHOICES, blank=True)
    summary = EncryptedTextField(blank=True)
    denial_reason = EncryptedTextField(blank=True)
    recommendation_reason = EncryptedTextField(blank=True)
    checklist = models.JSONField(default=list, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    appeal_letter = EncryptedTextField(blank=True)

    # The dental team's answers to the letter's [BRACKETED] items, which the AI
    # then works into the letter. JSON list; encrypted because the dentist's
    # answers are clinical details.
    review_answers_json = EncryptedTextField(blank=True)
    revision_notes = models.JSONField(default=list, blank=True)

    class Meta(SoftDeleteModel.Meta):
        ordering = ['-created_at']

    def __str__(self):
        return f"Denial on invoice #{self.invoice_id} ({self.get_status_display()})"

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES

    @property
    def ai_is_stuck(self):
        # The analysis runs in a background thread; if the server restarted
        # mid-analysis it never finishes, so offer a retry after a while.
        from django.utils import timezone
        return (self.ai_status == 'processing' and self.ai_started_at is not None
                and timezone.now() - self.ai_started_at > datetime.timedelta(minutes=10))

    @property
    def review_answers(self):
        return json.loads(self.review_answers_json) if self.review_answers_json else []

    @review_answers.setter
    def review_answers(self, answers):
        self.review_answers_json = json.dumps(answers)

    @property
    def days_until_deadline(self):
        from django.utils import timezone
        if not self.appeal_deadline:
            return None
        return (self.appeal_deadline - timezone.localdate()).days


class AIUsage(models.Model):
    """One AI request (an analysis or a letter update), for the daily cap."""
    created_at = models.DateTimeField(auto_now_add=True)
    task = models.CharField(max_length=10)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    class Meta:
        ordering = ['-created_at']

    @classmethod
    def limit_reached(cls, user):
        """True when the site-wide AI_DAILY_LIMIT is used up. Superusers are
        exempt so the owner can always run a live demo."""
        from django.utils import timezone
        limit = settings.AI_DAILY_LIMIT
        if not limit or user.is_superuser:
            return False
        start_of_day = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        return cls.objects.filter(created_at__gte=start_of_day).count() >= limit
