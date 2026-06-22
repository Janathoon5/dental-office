from django import forms
from .models import Invoice, Payment


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ['patient', 'appointment', 'subtotal', 'insurance_amount', 'status', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['amount', 'method', 'notes']
