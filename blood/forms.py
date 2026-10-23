from datetime import date

from django import forms

from .models import Donation, BloodRequest, PatientProfile


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


class BloodRequestForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['blood_group'].label = 'Required Blood Group'
        self.fields['units'].label = 'Number of Units'
        self.fields['needed_by_date'].label = 'Needed By Date'
        self.fields['notes'].label = 'Reason / Additional Notes'

        for field_name, field in self.fields.items():
            field.widget.attrs.update({
                'class': 'form-control',
            })

        self.fields['notes'].widget.attrs.update({
            'rows': 4,
            'placeholder': 'Optional: mention the reason or any extra details...'
        })
        self.fields['needed_by_date'].widget.attrs.update({
            'type': 'date',
            'placeholder': 'Select the date needed'
        })

    def clean_units(self):
        units = self.cleaned_data.get('units')
        if units is None or units <= 0:
            raise forms.ValidationError('Units required must be at least 1.')
        return units

    def clean_needed_by_date(self):
        needed_by_date = self.cleaned_data.get('needed_by_date')
        if not needed_by_date:
            raise forms.ValidationError('This field is required.')
        if needed_by_date < date.today():
            raise forms.ValidationError('Needed by date cannot be in the past.')
        return needed_by_date

    class Meta:
        model = BloodRequest
        fields = ['blood_group', 'units', 'needed_by_date', 'notes']
        widgets = {
            'needed_by_date': forms.DateInput(
                attrs={'type': 'date'}
            ),
            'notes': forms.Textarea(
                attrs={'rows': 3}
            ),
        }


class PatientProfileForm(forms.ModelForm):
    """
    BB-F-008: Patient Profile Form
    Allows patients to maintain and update their profile details.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['blood_group'].label = 'Blood Group'
        self.fields['age'].label = 'Age'
        self.fields['disease'].label = 'Medical Reason / Condition'
        self.fields['contact_phone'].label = 'Contact Phone Number'
        self.fields['address'].label = 'Residential Address'

        for field_name, field in self.fields.items():
            field.widget.attrs.update({
                'class': 'form-control',
            })

        self.fields['age'].widget.attrs.update({
            'placeholder': 'Enter age (e.g. 28)',
            'min': '1',
            'max': '125',
        })
        self.fields['disease'].widget.attrs.update({
            'placeholder': 'Reason for blood requirement (e.g. Surgery, Anemia)',
        })
        self.fields['contact_phone'].widget.attrs.update({
            'placeholder': 'e.g. +91 9876543210',
        })
        self.fields['address'].widget.attrs.update({
            'rows': 3,
            'placeholder': 'Enter your residential address...',
        })

    def clean_age(self):
        age = self.cleaned_data.get('age')
        if age is not None and (age <= 0 or age > 125):
            raise forms.ValidationError('Please enter a valid age between 1 and 125.')
        return age

    class Meta:
        model = PatientProfile
        fields = ['blood_group', 'age', 'disease', 'contact_phone', 'address']

