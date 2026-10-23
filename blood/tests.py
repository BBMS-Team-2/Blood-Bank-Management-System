
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib import admin
from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse

from .admin import DonationAdmin
from .models import BloodInventory, Donation
from .services import review_donation


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


class DonationReviewServiceTests(TestCase):
    def setUp(self):
        self.donor = User.objects.create_user(username="review_donor")
        self.reviewer = User.objects.create_user(
            username="reviewer",
            is_staff=True,
        )

    def create_donation(self, units=2, blood_group="O+"):
        return Donation.objects.create(
            donor=self.donor,
            blood_group=blood_group,
            donation_date=date.today(),
            units=units,
        )

    def test_approving_pending_donation_adds_exact_units(self):
        donation = self.create_donation(units=3)
        inventory = BloodInventory.objects.create(
            blood_group="O+",
            units=5,
        )

        self.assertTrue(
            review_donation(donation.id, self.reviewer, "approve")
        )

        donation.refresh_from_db()
        inventory.refresh_from_db()
        self.assertEqual(donation.status, "Approved")
        self.assertEqual(donation.reviewed_by, self.reviewer)
        self.assertIsNotNone(donation.reviewed_at)
        self.assertEqual(inventory.units, 8)

    def test_rejecting_pending_donation_does_not_add_inventory(self):
        donation = self.create_donation(units=3)

        self.assertTrue(
            review_donation(donation.id, self.reviewer, "reject")
        )

        donation.refresh_from_db()
        self.assertEqual(donation.status, "Rejected")
        self.assertFalse(
            BloodInventory.objects.filter(blood_group="O+").exists()
        )

    def test_reviewed_donation_can_only_be_reviewed_once(self):
        donation = self.create_donation(units=3)

        self.assertTrue(
            review_donation(donation.id, self.reviewer, "approve")
        )
        self.assertFalse(
            review_donation(donation.id, self.reviewer, "reject")
        )
        self.assertFalse(
            review_donation(donation.id, self.reviewer, "approve")
        )

        self.assertEqual(
            BloodInventory.objects.get(blood_group="O+").units,
            3,
        )
        donation.refresh_from_db()
        self.assertEqual(donation.status, "Approved")

    def test_invalid_action_raises_value_error(self):
        donation = self.create_donation()

        with self.assertRaisesMessage(
            ValueError,
            "Action must be 'approve' or 'reject'.",
        ):
            review_donation(donation.id, self.reviewer, "hold")

        donation.refresh_from_db()
        self.assertEqual(donation.status, "Pending")

    def test_nonexistent_donation_returns_false_without_inventory_change(self):
        self.assertFalse(
            review_donation(999999, self.reviewer, "approve")
        )
        self.assertFalse(BloodInventory.objects.exists())


class DonationReviewWorkflowTests(TestCase):
    def setUp(self):
        self.donor = User.objects.create_user(username="workflow_donor")
        self.reviewer = User.objects.create_user(
            username="workflow_reviewer",
            is_staff=True,
        )
        self.client.force_login(self.reviewer)
        self.donation = Donation.objects.create(
            donor=self.donor,
            blood_group="A+",
            donation_date=date.today(),
            units=2,
        )

    def test_staff_review_page_uses_shared_approval_logic(self):
        response = self.client.post(
            reverse(
                "review_donation",
                kwargs={"donation_id": self.donation.id},
            ),
            {"action": "approve"},
        )

        self.assertRedirects(response, reverse("manage_donations"))
        self.assertEqual(
            BloodInventory.objects.get(blood_group="A+").units,
            2,
        )

    def test_staff_review_page_handles_invalid_and_missing_reviews(self):
        invalid_response = self.client.post(
            reverse(
                "review_donation",
                kwargs={"donation_id": self.donation.id},
            ),
            {"action": "invalid"},
        )
        missing_response = self.client.post(
            reverse(
                "review_donation",
                kwargs={"donation_id": 999999},
            ),
            {"action": "approve"},
        )

        self.assertRedirects(
            invalid_response,
            reverse("manage_donations"),
        )
        self.assertRedirects(
            missing_response,
            reverse("manage_donations"),
        )
        self.assertEqual(
            Donation.objects.get(pk=self.donation.id).status,
            "Pending",
        )
        self.assertFalse(BloodInventory.objects.exists())

    def test_admin_approval_uses_the_same_review_logic(self):
        model_admin = DonationAdmin(Donation, admin.site)
        queryset = Donation.objects.filter(pk=self.donation.id)
        request = SimpleNamespace(user=self.reviewer)

        with patch.object(model_admin, "message_user") as message_user:
            model_admin.approve_donations(request, queryset)

        self.donation.refresh_from_db()
        self.assertEqual(self.donation.status, "Approved")
        self.assertEqual(
            BloodInventory.objects.get(blood_group="A+").units,
            2,
        )
        message_user.assert_called_once()
