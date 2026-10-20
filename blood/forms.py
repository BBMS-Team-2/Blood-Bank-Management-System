
from django import forms
from .models import Donation


class DonationForm(forms.ModelForm):
    class Meta:
        model = Donation
        fields = ['blood_group', 'donation_date', 'units', 'notes']
        widgets = {
            'donation_date': forms.DateInput(
                attrs={'type': 'date'}
            ),
            'notes': forms.Textarea(
                attrs={'rows': 3}
            ),
        }
