from django import forms
from .models import Patient, MedicalAlert


class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = [
            'first_name', 'last_name', 'date_of_birth', 'phone', 'email',
            'address', 'insurance_provider', 'insurance_id', 'allergies', 'medical_notes',
            'recall_interval_months',
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'address': forms.Textarea(attrs={'rows': 3}),
            'allergies': forms.Textarea(attrs={'rows': 3}),
            'medical_notes': forms.Textarea(attrs={'rows': 4}),
        }

    # Only shown once a possible duplicate has been found.
    confirm_duplicate = forms.BooleanField(required=False)

    def clean(self):
        cleaned_data = super().clean()
        first, last = cleaned_data.get('first_name'), cleaned_data.get('last_name')
        dob = cleaned_data.get('date_of_birth')
        self.duplicate = None
        if first and last and dob and not cleaned_data.get('confirm_duplicate'):
            matches = Patient.objects.filter(first_name__iexact=first.strip(), last_name__iexact=last.strip(),
                                             date_of_birth=dob).exclude(pk=self.instance.pk)
            self.duplicate = matches.first()
            if self.duplicate:
                raise forms.ValidationError(
                    f'{self.duplicate.full_name()}, born {dob:%B} {dob.day}, {dob.year}, is already a patient.'
                )
        return cleaned_data


class NewPatientForm(PatientForm):
    """Just the details needed to add a patient while booking their
    appointment request; the rest can be filled in at the first visit."""
    class Meta(PatientForm.Meta):
        fields = ['first_name', 'last_name', 'date_of_birth', 'phone', 'email']


class MedicalAlertForm(forms.ModelForm):
    class Meta:
        model = MedicalAlert
        fields = ['alert_type', 'severity', 'description']
        widgets = {
            'description': forms.TextInput(attrs={'placeholder': 'e.g. Allergic to penicillin'}),
        }
