from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.contrib.auth.models import User
from django.db.models import Q
from django.core.validators import MinValueValidator


class Donation(models.Model):
    BLOOD_GROUPS = [
        ('A+', 'A+'),
        ('A-', 'A-'),
        ('B+', 'B+'),
        ('B-', 'B-'),
        ('AB+', 'AB+'),
        ('AB-', 'AB-'),
        ('O+', 'O+'),
        ('O-', 'O-'),
    ]

    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
        ('Cancelled', 'Cancelled'),
    ]

    donor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='donations'
    )
    blood_group = models.CharField(
        max_length=3,
        choices=BLOOD_GROUPS,
        db_index=True
    )
    donation_date = models.DateField(db_index=True)
    expiry_date = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        help_text='Recorded expiration date of donated blood units (defaults to donation date + 42 days)'
    )
    units = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='Pending',
        db_index=True
    )
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_donations'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['blood_group', 'status', 'expiry_date'], name='donation_bg_stat_exp_idx'),
            models.Index(fields=['donor', '-donation_date'], name='donation_donor_date_idx'),
            models.Index(fields=['status', '-created_at'], name='donation_stat_created_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(units__gte=1),
                name='donation_units_positive',
            ),
        ]

    def clean(self):
        super().clean()
        if self.units is not None and self.units < 1:
            raise ValidationError({'units': 'Units donated must be at least 1.'})
        if self.donation_date and self.donation_date > date.today():
            raise ValidationError({'donation_date': 'Donation date cannot be in the future.'})
        if self.donation_date and self.expiry_date and self.expiry_date < self.donation_date:
            raise ValidationError({'expiry_date': 'Expiry date cannot be earlier than donation date.'})

    def save(self, *args, **kwargs):
        if not self.expiry_date and self.donation_date:
            self.expiry_date = self.donation_date + timedelta(days=42)
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.donor.username} - {self.blood_group} - {self.status}"


class BloodRequest(models.Model):
    BLOOD_GROUPS = Donation.BLOOD_GROUPS
    STATUS_CHOICES = Donation.STATUS_CHOICES

    patient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='blood_requests'
    )
    blood_group = models.CharField(
        max_length=3,
        choices=BLOOD_GROUPS,
        db_index=True
    )
    units = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    needed_by_date = models.DateField(db_index=True)
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='Pending',
        db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['patient', '-needed_by_date'], name='req_patient_date_idx'),
            models.Index(fields=['status', '-created_at'], name='req_stat_created_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(units__gte=1),
                name='bloodrequest_units_positive',
            ),
        ]

    def clean(self):
        super().clean()
        if self.units is not None and self.units < 1:
            raise ValidationError({'units': 'Units required must be at least 1.'})
        if self.needed_by_date and self.needed_by_date < date.today():
            raise ValidationError({'needed_by_date': 'Needed by date cannot be in the past.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.patient.username} - {self.blood_group} - {self.status}"


class BloodInventory(models.Model):
    blood_group = models.CharField(
        max_length=3,
        choices=Donation.BLOOD_GROUPS,
        unique=True
    )
    units = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    expiry_date = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        help_text='Earliest recorded expiry date for available units'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(units__gte=0),
                name='bloodinventory_units_non_negative',
            ),
        ]

    def clean(self):
        super().clean()
        if self.units is not None and self.units < 0:
            raise ValidationError({'units': 'Inventory units cannot be negative.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def nearest_expiry(self):
        if self.expiry_date:
            return self.expiry_date
        earliest = Donation.objects.filter(
            blood_group=self.blood_group,
            status='Approved',
            expiry_date__isnull=False
        ).order_by('expiry_date').first()
        return earliest.expiry_date if earliest else None

    def __str__(self):
        expiry_info = f" (expires {self.expiry_date})" if self.expiry_date else ""
        return f"{self.blood_group}: {self.units} units{expiry_info}"


class PatientProfile(models.Model):
    """
    BB-F-008: Patient Profile Management
    Stores profile details for patients submitting blood requests.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='patient_profile'
    )
    blood_group = models.CharField(
        max_length=3,
        choices=Donation.BLOOD_GROUPS,
        blank=True,
        db_index=True
    )
    age = models.PositiveSmallIntegerField(null=True, blank=True)
    disease = models.CharField(
        max_length=150,
        blank=True,
        help_text='Medical reason or condition requiring blood support'
    )
    contact_phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"PatientProfile: {self.user.username} ({self.blood_group or 'Unspecified'})"


class DonorProfile(models.Model):
    """
    BB-F-004: Donor Profile Management
    Stores profile details for registered blood donors.
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='donor_profile'
    )
    blood_group = models.CharField(
        max_length=3,
        choices=Donation.BLOOD_GROUPS,
        blank=True,
        db_index=True
    )
    age = models.PositiveSmallIntegerField(null=True, blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"DonorProfile: {self.user.username} ({self.blood_group or 'Unspecified'})"
