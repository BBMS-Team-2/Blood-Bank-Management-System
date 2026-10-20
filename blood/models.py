
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
        default='Pending',
        editable=False
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.donor.username} - {self.blood_group} - {self.status}"
