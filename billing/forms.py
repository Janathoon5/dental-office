from django import forms
from pathlib import Path

from .models import ClaimDenial, Invoice, Payment


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


MAX_LETTER_BYTES = 20 * 1024 * 1024
LETTER_EXTENSIONS = ('.pdf', '.jpg', '.jpeg', '.png', '.webp', '.gif')


class DenialUploadForm(forms.Form):
    letter = forms.FileField(
        widget=forms.ClearableFileInput(attrs={'accept': '.pdf,.jpg,.jpeg,.png,.webp,.gif,image/*'}),
    )
    confirm_no_phi = forms.BooleanField(
        required=False,
        label='This is a sample letter with no real patient information.',
    )

    def __init__(self, *args, require_no_phi_confirmation=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['confirm_no_phi'].required = require_no_phi_confirmation

    def clean_letter(self):
        letter = self.cleaned_data['letter']
        if Path(letter.name).suffix.lower() not in LETTER_EXTENSIONS:
            raise forms.ValidationError('Upload a PDF or a photo (JPG, PNG, WEBP).')
        if letter.size > MAX_LETTER_BYTES:
            raise forms.ValidationError('That file is over 20 MB. Try a smaller scan or photo.')
        return letter


class DenialUpdateForm(forms.ModelForm):
    class Meta:
        model = ClaimDenial
        fields = ['status', 'appeal_deadline', 'appeal_letter']
        widgets = {
            'appeal_deadline': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }
