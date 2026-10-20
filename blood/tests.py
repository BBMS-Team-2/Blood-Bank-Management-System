
from datetime import date

from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse

from .models import Donation


class DonationSubmissionTests(TestCase):
    def setUp(self):
        self.donor, _ = User.objects.get_or_create(
            username="test_donor"
        )
        self.client.force_login(self.donor)

    def test_donation_form_is_displayed(self):
        response = self.client.get(
            reverse("submit_donation")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Submit Blood Donation")

    def test_valid_donation_is_saved_as_pending(self):
        response = self.client.post(
            reverse("submit_donation"),
            {
                "blood_group": "O+",
                "donation_date": date.today().isoformat(),
                "units": 1,
                "notes": "Automated F005 test",
            },
        )

        self.assertEqual(response.status_code, 302)

        donation = Donation.objects.get(
            notes="Automated F005 test"
        )
        self.assertEqual(donation.donor, self.donor)
        self.assertEqual(donation.blood_group, "O+")
        self.assertEqual(donation.status, "Pending")

    def test_invalid_blood_group_is_rejected(self):
        response = self.client.post(
            reverse("submit_donation"),
            {
                "blood_group": "INVALID",
                "donation_date": date.today().isoformat(),
                "units": 1,
                "notes": "Invalid F005 test",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Donation.objects.filter(
                notes="Invalid F005 test"
            ).exists()
        )
