from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
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

    class Meta(SoftDeleteModel.Meta):
        pass

    def __str__(self):
        return f"${self.amount} on Invoice #{self.invoice.pk}"
