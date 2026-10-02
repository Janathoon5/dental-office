from django import forms
from dental_office.providers import ProviderChoiceField, limit_to_providers
from appointments.models import Appointment
from .models import TreatmentRecord, TreatmentPlan, TreatmentPlanItem, ToothCondition
from .validators import validate_tooth_list


class ToothNumberMixin:
    def clean_tooth_number(self):
        tooth = self.cleaned_data['tooth_number'].strip()
        validate_tooth_list(tooth)
        return tooth


class TreatmentRecordForm(ToothNumberMixin, forms.ModelForm):
    class Meta:
        model = TreatmentRecord
        fields = ['patient', 'appointment', 'dentist', 'date', 'procedure', 'tooth_number', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 4}),
        }
        field_classes = {'dentist': ProviderChoiceField}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        limit_to_providers(self.fields['dentist'], current=self.instance.dentist if self.instance.pk else None)
        # Only this patient's visits, newest first, not every appointment on file.
        patient = self.instance.patient_id or self.initial.get('patient') or self.data.get('patient')
        patient_id = getattr(patient, 'pk', patient)
        appointments = Appointment.objects.filter(patient_id=patient_id) if patient_id else Appointment.objects.none()
        self.fields['appointment'].queryset = appointments.order_by('-date', '-start_time')


class TreatmentPlanForm(forms.ModelForm):
    class Meta:
        model = TreatmentPlan
        fields = ['patient', 'title', 'status', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }


class TreatmentPlanItemForm(ToothNumberMixin, forms.ModelForm):
    """Adding an item: it always starts as Pending."""
    class Meta:
        model = TreatmentPlanItem
        fields = ['procedure', 'tooth_number', 'estimated_cost']


class TreatmentPlanItemEditForm(ToothNumberMixin, forms.ModelForm):
    class Meta:
        model = TreatmentPlanItem
        fields = ['procedure', 'tooth_number', 'estimated_cost', 'status']


class ToothConditionForm(forms.ModelForm):
    class Meta:
        model = ToothCondition
        fields = ['condition', 'notes']
