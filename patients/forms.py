from django import forms
from .models import Patient, MedicalAlert


class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = [
            'first_name', 'last_name', 'date_of_birth', 'phone', 'email',
            'address', 'insurance_provider', 'insurance_id', 'allergies', 'medical_notes',
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'address': forms.Textarea(attrs={'rows': 3}),
            'allergies': forms.Textarea(attrs={'rows': 3}),
            'medical_notes': forms.Textarea(attrs={'rows': 4}),
        }


class MedicalAlertForm(forms.ModelForm):
    class Meta:
        model = MedicalAlert
        fields = ['alert_type', 'severity', 'description']
        widgets = {
            'description': forms.TextInput(attrs={'placeholder': 'e.g. Allergic to penicillin'}),
        }
