from datetime import date, timedelta

from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse

from .models import Donation, BloodRequest, BloodInventory


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


class BloodAvailabilityTests(TestCase):
    """
    BB-F-011: View Blood Availability (TC-INV-01)
    """
    def test_blood_availability_displays_all_blood_groups_with_defaults(self):
        response = self.client.get(reverse("blood_availability"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Blood Availability")
        
        # Verify context contains all 8 standard blood groups
        groups_in_context = [item["blood_group"] for item in response.context["blood_groups"]]
        for group, _ in Donation.BLOOD_GROUPS:
            self.assertIn(group, groups_in_context)
            self.assertContains(response, f"card-{group}")
        
        self.assertEqual(response.context["total_units"], 0)

    def test_blood_availability_reflects_actual_inventory_records(self):
        BloodInventory.objects.create(blood_group="A+", units=15)
        BloodInventory.objects.create(blood_group="O-", units=3)
        BloodInventory.objects.create(blood_group="B+", units=0)

        response = self.client.get(reverse("blood_availability"))
        self.assertEqual(response.status_code, 200)

        data = {item["blood_group"]: item for item in response.context["blood_groups"]}
        self.assertEqual(data["A+"]["units"], 15)
        self.assertEqual(data["A+"]["status"], "Available")
        self.assertEqual(data["O-"]["units"], 3)
        self.assertEqual(data["O-"]["status"], "Low Stock")
        self.assertEqual(data["B+"]["units"], 0)
        self.assertEqual(data["B+"]["status"], "Out of Stock")

        self.assertEqual(response.context["total_units"], 18)
        self.assertContains(response, "18")

    def test_view_is_read_only_and_does_not_mutate_inventory(self):
        BloodInventory.objects.create(blood_group="AB+", units=7)
        # Attempting POST does not mutate inventory records
        response = self.client.post(
            reverse("blood_availability"),
            {"blood_group": "AB+", "units": 999}
        )
        self.assertEqual(response.status_code, 200)
        inv = BloodInventory.objects.get(blood_group="AB+")
        self.assertEqual(inv.units, 7)

