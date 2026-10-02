from django import forms
from dental_office.providers import ProviderChoiceField, limit_to_providers
from .models import TreatmentRecord, TreatmentPlan, TreatmentPlanItem, ToothCondition


class TreatmentRecordForm(forms.ModelForm):
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


class TreatmentPlanForm(forms.ModelForm):
    class Meta:
        model = TreatmentPlan
        fields = ['patient', 'title', 'status', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }


class TreatmentPlanItemForm(forms.ModelForm):
    """Adding an item: it always starts as Pending."""
    class Meta:
        model = TreatmentPlanItem
        fields = ['procedure', 'tooth_number', 'estimated_cost']


class TreatmentPlanItemEditForm(forms.ModelForm):
    class Meta:
        model = TreatmentPlanItem
        fields = ['procedure', 'tooth_number', 'estimated_cost', 'status']


class ToothConditionForm(forms.ModelForm):
    class Meta:
        model = ToothCondition
        fields = ['condition', 'notes']
