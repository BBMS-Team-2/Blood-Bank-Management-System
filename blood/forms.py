from datetime import date

from django import forms

from .models import Donation


class DonationForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['blood_group'].label = 'Blood Group'
        self.fields['donation_date'].label = 'Donation Date'
        self.fields['units'].label = 'Units Donated'
        self.fields['notes'].label = 'Notes'

        for field_name, field in self.fields.items():
            field.widget.attrs.update({
                'class': 'form-control',
            })

        self.fields['notes'].widget.attrs.update({
            'rows': 4,
            'placeholder': 'Optional: add any relevant donation notes...'
        })
        self.fields['donation_date'].widget.attrs.update({
            'type': 'date',
            'placeholder': 'Select donation date'
        })

    def clean_units(self):
        units = self.cleaned_data.get('units')
        if units is None or units <= 0:
            raise forms.ValidationError('Units donated must be at least 1.')
        return units

    def clean_donation_date(self):
        donation_date = self.cleaned_data.get('donation_date')
        if donation_date and donation_date > date.today():
            raise forms.ValidationError(
                'Donation date cannot be in the future.'
            )
        return donation_date

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
