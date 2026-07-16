from django import forms

from .models import DentalImage
from .validators import validate_dental_image


class StaffImageUploadForm(forms.ModelForm):
    class Meta:
        model = DentalImage
        fields = ['image_type', 'image', 'captured_date', 'tooth_number', 'caption']
        widgets = {
            'captured_date': forms.DateInput(attrs={'type': 'date'}),
            'caption': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_image(self):
        image = self.cleaned_data['image']
        validate_dental_image(image)
        return image


class PatientImageUploadForm(forms.ModelForm):
    class Meta:
        model = DentalImage
        fields = ['image', 'captured_date', 'caption']
        widgets = {
            'captured_date': forms.DateInput(attrs={'type': 'date'}),
            'caption': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Anything the dentist should know about this photo (optional)'}),
        }

    def clean_image(self):
        image = self.cleaned_data['image']
        validate_dental_image(image)
        return image
