from datetime import date, timedelta

from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse

from .models import Donation, BloodRequest


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


class BloodRequestSubmissionTests(TestCase):
    def setUp(self):
        self.patient, _ = User.objects.get_or_create(
            username="test_patient"
        )

    def test_request_form_is_displayed_for_authenticated_patient(self):
        self.client.force_login(self.patient)

        response = self.client.get(
            reverse("submit_blood_request")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Submit Blood Request")

    def test_valid_request_is_saved_successfully(self):
        self.client.force_login(self.patient)

        response = self.client.post(
            reverse("submit_blood_request"),
            {
                "blood_group": "O-",
                "units": 2,
                "needed_by_date": (date.today() + timedelta(days=3)).isoformat(),
                "notes": "Urgent surgery support",
            },
        )

        self.assertEqual(response.status_code, 302)
        request = BloodRequest.objects.get(
            notes="Urgent surgery support"
        )
        self.assertEqual(request.patient, self.patient)
        self.assertEqual(request.blood_group, "O-")
        self.assertEqual(request.units, 2)
        self.assertEqual(request.status, "Pending")

    def test_invalid_request_input_is_rejected(self):
        self.client.force_login(self.patient)

        response = self.client.post(
            reverse("submit_blood_request"),
            {
                "blood_group": "INVALID",
                "units": 0,
                "needed_by_date": (date.today() - timedelta(days=1)).isoformat(),
                "notes": "Bad request",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            BloodRequest.objects.filter(
                notes="Bad request"
            ).exists()
        )

    def test_unauthenticated_user_cannot_submit_request(self):
        response = self.client.get(
            reverse("submit_blood_request")
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response.url)
