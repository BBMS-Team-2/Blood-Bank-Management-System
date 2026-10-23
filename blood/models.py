from django.db import models
from django.contrib.auth.models import User


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
    ]

    donor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='donations'
    )
    blood_group = models.CharField(
        max_length=3,
        choices=BLOOD_GROUPS
    )
    donation_date = models.DateField()
    units = models.PositiveSmallIntegerField(default=1)
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='Pending'
    )
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_donations'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

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
        choices=BLOOD_GROUPS
    )
    units = models.PositiveSmallIntegerField(default=1)
    needed_by_date = models.DateField()
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='Pending'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.patient.username} - {self.blood_group} - {self.status}"


class BloodInventory(models.Model):
    blood_group = models.CharField(
        max_length=3,
        choices=Donation.BLOOD_GROUPS,
        unique=True
    )
    units = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.blood_group}: {self.units} units"


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
        blank=True
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

