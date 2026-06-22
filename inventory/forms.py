from django import forms
from .models import SupplyItem


class SupplyItemForm(forms.ModelForm):
    class Meta:
        model = SupplyItem
        fields = ['name', 'category', 'quantity', 'unit', 'min_quantity', 'notes']
