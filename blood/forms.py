from datetime import date

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Donation, BloodRequest, PatientProfile, DonorProfile


class DonationForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['blood_group'].label = 'Blood Group'
        self.fields['donation_date'].label = 'Donation Date'
        self.fields['expiry_date'].label = 'Expiry Date'
        self.fields['expiry_date'].required = False
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
        self.fields['expiry_date'].widget.attrs.update({
            'type': 'date',
            'placeholder': 'Optional: auto-calculated if left blank'
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

    def clean_expiry_date(self):
        expiry_date = self.cleaned_data.get('expiry_date')
        donation_date = self.cleaned_data.get('donation_date')
        if expiry_date and donation_date and expiry_date < donation_date:
            raise forms.ValidationError(
                'Expiry date cannot be earlier than donation date.'
            )
        return expiry_date

    class Meta:
        model = Donation
        fields = ['blood_group', 'donation_date', 'expiry_date', 'units', 'notes']
        widgets = {
            'donation_date': forms.DateInput(
                attrs={'type': 'date'}
            ),
            'expiry_date': forms.DateInput(
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
        self.fields['emergency_contact_name'].label = 'Emergency Contact Name'
        self.fields['emergency_contact_phone'].label = 'Emergency Contact Phone'
        self.fields['hospital_name'].label = 'Admitting Hospital / Medical Center'
        self.fields['attending_physician'].label = 'Attending Doctor / Physician'

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
        self.fields['emergency_contact_name'].widget.attrs.update({
            'placeholder': 'Full name of emergency contact person',
        })
        self.fields['emergency_contact_phone'].widget.attrs.update({
            'placeholder': 'Emergency phone number (e.g. +91 9876543211)',
        })
        self.fields['hospital_name'].widget.attrs.update({
            'placeholder': 'e.g. Manipal Hospital, Bengaluru',
        })
        self.fields['attending_physician'].widget.attrs.update({
            'placeholder': 'e.g. Dr. Ramesh Kumar',
        })

    def clean_age(self):
        age = self.cleaned_data.get('age')
        if age is not None and (age <= 0 or age > 125):
            raise forms.ValidationError('Please enter a valid age between 1 and 125.')
        return age

    class Meta:
        model = PatientProfile
        fields = [
            'blood_group',
            'age',
            'disease',
            'contact_phone',
            'address',
            'emergency_contact_name',
            'emergency_contact_phone',
            'hospital_name',
            'attending_physician',
        ]


class DonorProfileForm(forms.ModelForm):
    """
    BB-F-004: Donor Profile Form
    Allows registered donors to view and update their profile details.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['blood_group'].label = 'Blood Group'
        self.fields['age'].label = 'Age'
        self.fields['contact_phone'].label = 'Contact Phone Number'
        self.fields['address'].label = 'Residential Address'

        for field_name, field in self.fields.items():
            field.widget.attrs.update({
                'class': 'form-control',
            })

        self.fields['age'].widget.attrs.update({
            'placeholder': 'Enter age (e.g. 25)',
            'min': '18',
            'max': '65',
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
        if age is not None and (age < 18 or age > 65):
            raise forms.ValidationError('Blood donors must be between 18 and 65 years of age.')
        return age

    class Meta:
        model = DonorProfile
        fields = ['blood_group', 'age', 'contact_phone', 'address']


class UserRegisterForm(UserCreationForm):
    """
    BB-NF-003, BB-F-001: Secure User Registration
    Uses Django's cryptographic password hashing (PBKDF2) and strong validation.
    Enforces healthcare-grade password complexity (length, casing, numerical digits).
    """
    email = forms.EmailField(required=True, label='Email Address')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({
                'class': 'form-control',
            })
        if 'username' in self.fields:
            self.fields['username'].widget.attrs.update({'placeholder': 'Choose a unique username'})
        if 'email' in self.fields:
            self.fields['email'].widget.attrs.update({'placeholder': 'e.g. user@hospital.org'})
        if 'password1' in self.fields:
            self.fields['password1'].widget.attrs.update({'placeholder': 'Create a strong password (min 8 chars)'})
        if 'password2' in self.fields:
            self.fields['password2'].widget.attrs.update({'placeholder': 'Confirm your password'})

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')

        if password1 and password2 and password1 == password2:
            if len(password1) < 8:
                self.add_error('password1', forms.ValidationError("Password must contain at least 8 characters."))
            elif not any(c.isupper() for c in password1):
                self.add_error('password1', forms.ValidationError("Password must contain at least one uppercase letter (A-Z)."))
            elif not any(c.islower() for c in password1):
                self.add_error('password1', forms.ValidationError("Password must contain at least one lowercase letter (a-z)."))
            elif not any(c.isdigit() for c in password1):
                self.add_error('password1', forms.ValidationError("Password must contain at least one numerical digit (0-9)."))

        return cleaned_data

    class Meta:
        model = User
        fields = ['username', 'email']


class BloodInventoryUpdateForm(forms.Form):
    """Admin-only form for maintaining blood inventory stock by blood group."""
    blood_group = forms.ChoiceField(choices=Donation.BLOOD_GROUPS, label='Blood Group')
    units = forms.IntegerField(min_value=0, label='Units in Stock')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs.update({'class': 'form-control'})
        self.fields['units'].widget.attrs.update({
            'min': '0',
            'placeholder': 'Enter stock count',
        })

    def clean_units(self):
        units = self.cleaned_data.get('units')
        if units is None or units < 0:
            raise forms.ValidationError('Inventory units cannot be negative.')
        return units
