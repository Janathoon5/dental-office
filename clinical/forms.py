from django import forms
from .models import TreatmentRecord, TreatmentPlan, TreatmentPlanItem


class TreatmentRecordForm(forms.ModelForm):
    class Meta:
        model = TreatmentRecord
        fields = ['patient', 'appointment', 'dentist', 'date', 'procedure', 'tooth_number', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 4}),
        }


class TreatmentPlanForm(forms.ModelForm):
    class Meta:
        model = TreatmentPlan
        fields = ['patient', 'title', 'status', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }


class TreatmentPlanItemForm(forms.ModelForm):
    class Meta:
        model = TreatmentPlanItem
        fields = ['procedure', 'tooth_number', 'estimated_cost', 'status']
