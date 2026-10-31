import time
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.contrib import admin
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from .admin import DonationAdmin
from .models import BloodInventory, BloodRequest, Donation, PatientProfile, DonorProfile
from .services import review_donation, review_blood_request, set_user_active_status, check_login_lockout


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

    def test_blood_availability_includes_metrics_and_compatibility(self):
        BloodInventory.objects.create(blood_group="A+", units=10)
        BloodInventory.objects.create(blood_group="O-", units=2)
        # Other groups remain 0 units

        response = self.client.get(reverse("blood_availability"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["available_count"], 1)
        self.assertEqual(response.context["low_stock_count"], 1)
        self.assertEqual(response.context["out_of_stock_count"], 6)

        # Check compatibility badge on Universal Donor O-
        self.assertContains(response, "Universal Red Cell Donor")
        self.assertContains(response, "Universal Recipient")

    def test_quick_action_prefills_donation_and_request_blood_group(self):
        user = User.objects.create_user(username="quick_action_user", password="password123")
        self.client.force_login(user)

        # Check prefill in request form
        res_req = self.client.get(reverse("submit_blood_request") + "?blood_group=B+")
        self.assertEqual(res_req.status_code, 200)
        self.assertEqual(res_req.context["form"].initial.get("blood_group"), "B+")

        # Check prefill in donation form
        res_don = self.client.get(reverse("submit_donation") + "?blood_group=O-")
        self.assertEqual(res_don.status_code, 200)
        self.assertEqual(res_don.context["form"].initial.get("blood_group"), "O-")


class DonationHistoryTests(TestCase):
    """
    BB-F-007: Donation History (TC-DON-04, BB-SR-003)
    """
    def setUp(self):
        self.donor1 = User.objects.create_user(
            username="donor_one",
            password="password123"
        )
        self.donor2 = User.objects.create_user(
            username="donor_two",
            password="password123"
        )

        self.d1_donation = Donation.objects.create(
            donor=self.donor1,
            blood_group="A+",
            donation_date=date.today(),
            units=2,
            notes="Donor 1 donation",
            status="Approved"
        )
        self.d2_donation = Donation.objects.create(
            donor=self.donor2,
            blood_group="B-",
            donation_date=date.today(),
            units=1,
            notes="Donor 2 private donation",
            status="Pending"
        )

    def test_donor_can_view_own_donation_history(self):
        self.client.force_login(self.donor1)
        response = self.client.get(reverse("donation_history"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Donation History")
        self.assertContains(response, "Donor 1 donation")
        self.assertContains(response, "Approved")
        self.assertEqual(len(response.context["donations"]), 1)
        self.assertEqual(response.context["donations"][0], self.d1_donation)

    def test_donor_cannot_view_other_donor_history(self):
        # Authenticated as donor1, donor2's private donation must NOT appear
        self.client.force_login(self.donor1)
        response = self.client.get(reverse("donation_history"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Donor 2 private donation")
        self.assertNotContains(response, f"donation-row-{self.d2_donation.id}")

    def test_empty_donation_history_shows_empty_state(self):
        new_donor = User.objects.create_user(
            username="new_donor",
            password="password123"
        )
        self.client.force_login(new_donor)
        response = self.client.get(reverse("donation_history"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No Donations Recorded")
        self.assertEqual(len(response.context["donations"]), 0)

    def test_unauthenticated_access_redirects_to_login(self):
        response = self.client.get(reverse("donation_history"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response.url)

    def test_donation_history_calculates_lifetime_metrics_and_tier(self):
        self.client.force_login(self.donor1)
        response = self.client.get(reverse("donation_history"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_units_donated"], 2)
        self.assertEqual(response.context["estimated_lives_saved"], 6)
        self.assertEqual(response.context["donor_tier"], "Bronze Donor")
        self.assertContains(response, "Bronze Donor")
        self.assertContains(response, "Estimated Lives Saved")

    def test_next_eligible_donation_date_countdown(self):
        # Donation made today requires waiting 56 days
        self.client.force_login(self.donor1)
        res_recent = self.client.get(reverse("donation_history"))
        self.assertEqual(res_recent.status_code, 200)
        self.assertFalse(res_recent.context["is_eligible"])
        self.assertEqual(res_recent.context["days_remaining"], 56)

        # Donor with older donation (>56 days ago) is eligible
        eligible_donor = User.objects.create_user(username="eligible_donor", password="password123")
        Donation.objects.create(
            donor=eligible_donor,
            blood_group="O+",
            donation_date=date.today() - timedelta(days=60),
            units=1,
            status="Approved"
        )
        self.client.force_login(eligible_donor)
        res_eligible = self.client.get(reverse("donation_history"))
        self.assertEqual(res_eligible.status_code, 200)
        self.assertTrue(res_eligible.context["is_eligible"])
        self.assertEqual(res_eligible.context["days_remaining"], 0)
        self.assertContains(res_eligible, "You Are Eligible to Donate Today!")


class BloodRequestHistoryTests(TestCase):
    """
    BB-F-015: Blood Request History (TC-REQ-03, BB-SR-003)
    """
    def setUp(self):
        self.patient1 = User.objects.create_user(
            username="patient_one",
            password="password123"
        )
        self.patient2 = User.objects.create_user(
            username="patient_two",
            password="password123"
        )

        self.req1 = BloodRequest.objects.create(
            patient=self.patient1,
            blood_group="AB+",
            units=2,
            needed_by_date=date.today() + timedelta(days=2),
            notes="Patient 1 urgent surgery",
            status="Approved"
        )
        self.req2 = BloodRequest.objects.create(
            patient=self.patient2,
            blood_group="O-",
            units=3,
            needed_by_date=date.today() + timedelta(days=5),
            notes="Patient 2 private request",
            status="Pending"
        )

    def test_patient_can_view_own_request_history(self):
        self.client.force_login(self.patient1)
        response = self.client.get(reverse("blood_request_history"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Blood Requests")
        self.assertContains(response, "Patient 1 urgent surgery")
        self.assertContains(response, "Approved")
        self.assertEqual(len(response.context["blood_requests"]), 1)
        self.assertEqual(response.context["blood_requests"][0], self.req1)

    def test_patient_cannot_view_other_patient_request_history(self):
        # Patient 1 must not see Patient 2's request details
        self.client.force_login(self.patient1)
        response = self.client.get(reverse("blood_request_history"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Patient 2 private request")
        self.assertNotContains(response, f"request-row-{self.req2.id}")

    def test_empty_request_history_shows_empty_state(self):
        new_patient = User.objects.create_user(
            username="new_patient",
            password="password123"
        )
        self.client.force_login(new_patient)
        response = self.client.get(reverse("blood_request_history"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No Requests Submitted")
        self.assertEqual(len(response.context["blood_requests"]), 0)

    def test_unauthenticated_access_redirects_to_login(self):
        response = self.client.get(reverse("blood_request_history"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response.url)

    def test_request_history_displays_urgency_indicators_and_metrics(self):
        self.client.force_login(self.patient1)
        response = self.client.get(reverse("blood_request_history"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_requests"], 1)
        self.assertEqual(response.context["approved_count"], 1)
        self.assertEqual(response.context["pending_count"], 0)
        self.assertEqual(response.context["total_units_requested"], 2)
        self.assertContains(response, "Total Units Requested")

    def test_patient_can_cancel_own_pending_request(self):
        pending_req = BloodRequest.objects.create(
            patient=self.patient1,
            blood_group="B+",
            units=1,
            needed_by_date=date.today() + timedelta(days=3),
            status="Pending"
        )
        self.client.force_login(self.patient1)
        cancel_url = reverse("cancel_blood_request", kwargs={"request_id": pending_req.id})
        response = self.client.post(cancel_url)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("blood_request_history"))

        pending_req.refresh_from_db()
        self.assertEqual(pending_req.status, "Cancelled")

    def test_patient_cannot_cancel_other_patient_request(self):
        self.client.force_login(self.patient1)
        # Attempting to cancel patient2's pending request
        cancel_url = reverse("cancel_blood_request", kwargs={"request_id": self.req2.id})
        response = self.client.post(cancel_url)
        self.assertEqual(response.status_code, 302)

        self.req2.refresh_from_db()
        self.assertEqual(self.req2.status, "Pending")

    def test_patient_cannot_cancel_approved_request(self):
        self.client.force_login(self.patient1)
        cancel_url = reverse("cancel_blood_request", kwargs={"request_id": self.req1.id})
        response = self.client.post(cancel_url)
        self.assertEqual(response.status_code, 302)

        self.req1.refresh_from_db()
        self.assertEqual(self.req1.status, "Approved")


class PatientProfileManagementTests(TestCase):
    """
    BB-F-008: Patient Profile Management (TC-PAT-01)
    """
    def setUp(self):
        self.patient = User.objects.create_user(
            username="profile_patient",
            password="securepassword123"
        )

    def test_patient_can_view_profile_form(self):
        self.client.force_login(self.patient)
        response = self.client.get(reverse("patient_profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "profile_patient's Profile")
        self.assertIn("form", response.context)
        self.assertTrue(PatientProfile.objects.filter(user=self.patient).exists())

    def test_patient_can_update_permitted_details(self):
        self.client.force_login(self.patient)
        response = self.client.post(
            reverse("patient_profile"),
            {
                "blood_group": "AB-",
                "age": 34,
                "disease": "Chronic Anemia",
                "contact_phone": "+91-9876543210",
                "address": "123 Medical Avenue, Bengaluru",
            }
        )
        self.assertEqual(response.status_code, 302)
        profile = PatientProfile.objects.get(user=self.patient)
        self.assertEqual(profile.blood_group, "AB-")
        self.assertEqual(profile.age, 34)
        self.assertEqual(profile.disease, "Chronic Anemia")
        self.assertEqual(profile.contact_phone, "+91-9876543210")
        self.assertEqual(profile.address, "123 Medical Avenue, Bengaluru")

    def test_invalid_profile_data_is_rejected(self):
        self.client.force_login(self.patient)
        response = self.client.post(
            reverse("patient_profile"),
            {
                "blood_group": "INVALID",
                "age": 200,  # Invalid age
                "contact_phone": "123",
            }
        )
        self.assertEqual(response.status_code, 200)
        profile = PatientProfile.objects.get(user=self.patient)
        self.assertNotEqual(profile.age, 200)
        self.assertNotEqual(profile.blood_group, "INVALID")

    def test_unauthenticated_user_cannot_access_profile(self):
        response = self.client.get(reverse("patient_profile"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response.url)

    def test_patient_can_update_emergency_contact_and_hospital_facility(self):
        self.client.force_login(self.patient)
        response = self.client.post(
            reverse("patient_profile"),
            {
                "blood_group": "O+",
                "age": 28,
                "disease": "Thalassemia Minor",
                "contact_phone": "+91-9876543210",
                "address": "45 Richmond Circle, Bengaluru",
                "emergency_contact_name": "Rohan Breja",
                "emergency_contact_phone": "+91-9876500112",
                "hospital_name": "St. John's Medical Center",
                "attending_physician": "Dr. Arvind Swamy",
            }
        )
        self.assertEqual(response.status_code, 302)
        profile = PatientProfile.objects.get(user=self.patient)
        self.assertEqual(profile.emergency_contact_name, "Rohan Breja")
        self.assertEqual(profile.emergency_contact_phone, "+91-9876500112")
        self.assertEqual(profile.hospital_name, "St. John's Medical Center")
        self.assertEqual(profile.attending_physician, "Dr. Arvind Swamy")
        self.assertEqual(profile.completeness_percentage, 100)

    def test_patient_profile_completeness_calculation(self):
        profile = PatientProfile.objects.create(
            user=self.patient,
            blood_group="B+",
            age=30,
            contact_phone="+91-9876543210",
        )
        # 3 out of 8 fields filled: blood_group, age, contact_phone
        self.assertEqual(profile.completeness_percentage, int((3 / 8) * 100))

    def test_profile_renders_completeness_meter_and_facility_sections(self):
        self.client.force_login(self.patient)
        response = self.client.get(reverse("patient_profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Profile Completeness Status")
        self.assertContains(response, "Emergency Contact Information")
        self.assertContains(response, "Healthcare Facility Details")


class SecurityAndAuthenticationTests(TestCase):
    """
    BB-NF-003: Security & Password Protection (TC-SEC-01, TC-AUTH-01, BB-SR-001)
    """
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_password_is_cryptographically_hashed_and_not_plaintext(self):
        raw_password = "SuperSecretPassword123!"
        response = self.client.post(
            reverse("register"),
            {
                "username": "security_user",
                "email": "sec@example.com",
                "password1": raw_password,
                "password2": raw_password,
            }
        )
        self.assertEqual(response.status_code, 302)

        user = User.objects.get(username="security_user")
        # Ensure raw password is NEVER stored in database
        self.assertNotEqual(user.password, raw_password)
        # Ensure standard Django cryptographic hash algorithm prefix (PBKDF2/argon2)
        self.assertTrue(
            user.password.startswith("pbkdf2_") or user.password.startswith("argon2"),
            "Password must be stored using a cryptographic one-way hash algorithm."
        )
        self.assertTrue(user.check_password(raw_password))

    def test_password_complexity_validation_rules(self):
        # Missing uppercase
        res_no_upper = self.client.post(reverse("register"), {
            "username": "test_user_1",
            "email": "test1@example.com",
            "password1": "lowercase123!",
            "password2": "lowercase123!",
        })
        self.assertEqual(res_no_upper.status_code, 200)
        self.assertContains(res_no_upper, "at least one uppercase letter")

        # Missing lowercase
        res_no_lower = self.client.post(reverse("register"), {
            "username": "test_user_2",
            "email": "test2@example.com",
            "password1": "UPPERCASE123!",
            "password2": "UPPERCASE123!",
        })
        self.assertEqual(res_no_lower.status_code, 200)
        self.assertContains(res_no_lower, "at least one lowercase letter")

        # Missing digit
        res_no_digit = self.client.post(reverse("register"), {
            "username": "test_user_3",
            "email": "test3@example.com",
            "password1": "NoDigitsHere!",
            "password2": "NoDigitsHere!",
        })
        self.assertEqual(res_no_digit.status_code, 200)
        self.assertContains(res_no_digit, "at least one numerical digit")

        # Minimum length
        res_too_short = self.client.post(reverse("register"), {
            "username": "test_user_4",
            "email": "test4@example.com",
            "password1": "Sh1!",
            "password2": "Sh1!",
        })
        self.assertEqual(res_too_short.status_code, 200)
        self.assertContains(res_too_short, "at least 8 characters")

    def test_valid_credentials_authenticate_user_and_establish_session(self):
        User.objects.create_user(
            username="valid_user",
            password="CorrectPassword123"
        )
        response = self.client.post(
            reverse("login"),
            {
                "username": "valid_user",
                "password": "CorrectPassword123",
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    def test_invalid_credentials_are_rejected(self):
        User.objects.create_user(
            username="auth_user",
            password="CorrectPassword123"
        )
        response = self.client.post(
            reverse("login"),
            {
                "username": "auth_user",
                "password": "WrongPassword999",
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(response, "Invalid username or password")

    def test_failed_login_attempts_warn_and_trigger_lockout(self):
        User.objects.create_user(
            username="lockout_user",
            password="CorrectPassword123"
        )
        # First failed attempt
        r1 = self.client.post(reverse("login"), {"username": "lockout_user", "password": "BadPassword1"})
        self.assertContains(r1, "4 attempt(s) remaining before temporary lockout")

        # Attempts 2, 3, 4
        for _ in range(3):
            self.client.post(reverse("login"), {"username": "lockout_user", "password": "BadPassword"})

        # Attempt 5 triggers lockout
        r5 = self.client.post(reverse("login"), {"username": "lockout_user", "password": "BadPassword"})
        self.assertContains(r5, "Account is temporarily locked")

        # Subsequent attempt while locked out is rejected even with right credentials
        r6 = self.client.post(reverse("login"), {"username": "lockout_user", "password": "CorrectPassword123"})
        self.assertContains(r6, "Account is temporarily locked")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_successful_login_resets_failed_attempts(self):
        User.objects.create_user(
            username="retry_user",
            password="CorrectPassword123"
        )
        # Fail twice
        self.client.post(reverse("login"), {"username": "retry_user", "password": "BadPassword"})
        self.client.post(reverse("login"), {"username": "retry_user", "password": "BadPassword"})

        # Successful login
        res = self.client.post(reverse("login"), {"username": "retry_user", "password": "CorrectPassword123"})
        self.assertEqual(res.status_code, 302)

        # Confirm lock count was cleared
        is_locked, _, attempts = check_login_lockout("retry_user", "127.0.0.1")
        self.assertFalse(is_locked)
        self.assertEqual(attempts, 0)

    def test_logout_invalidates_session(self):
        user = User.objects.create_user(
            username="logout_user",
            password="Password123"
        )
        self.client.force_login(user)
        self.assertIn("_auth_user_id", self.client.session)

        response = self.client.get(reverse("logout"))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_session_cookie_security_settings(self):
        self.assertTrue(
            settings.SESSION_COOKIE_HTTPONLY,
            "SESSION_COOKIE_HTTPONLY must be True to protect against cookie theft."
        )
        self.assertTrue(
            settings.SESSION_EXPIRE_AT_BROWSER_CLOSE,
            "Session should expire at browser close for security."
        )



class DonorProfileManagementTests(TestCase):
    """
    BB-F-004: Donor Profile Management (TC-DON-01, BB-SR-002)
    """
    def setUp(self):
        self.donor = User.objects.create_user(
            username="profile_donor",
            password="securepassword123"
        )

    def test_donor_can_view_profile_form(self):
        self.client.force_login(self.donor)
        response = self.client.get(reverse("donor_profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "profile_donor's Profile")
        self.assertIn("form", response.context)
        self.assertTrue(DonorProfile.objects.filter(user=self.donor).exists())

    def test_donor_can_update_permitted_details(self):
        self.client.force_login(self.donor)
        response = self.client.post(
            reverse("donor_profile"),
            {
                "blood_group": "O+",
                "age": 28,
                "contact_phone": "+91-9876543210",
                "address": "456 Donor Boulevard, Bengaluru",
            }
        )
        self.assertEqual(response.status_code, 302)
        profile = DonorProfile.objects.get(user=self.donor)
        self.assertEqual(profile.blood_group, "O+")
        self.assertEqual(profile.age, 28)
        self.assertEqual(profile.contact_phone, "+91-9876543210")
        self.assertEqual(profile.address, "456 Donor Boulevard, Bengaluru")

    def test_invalid_profile_data_is_rejected(self):
        self.client.force_login(self.donor)
        response = self.client.post(
            reverse("donor_profile"),
            {
                "blood_group": "INVALID",
                "age": 200,  # Invalid age (exceeds donor criteria)
                "contact_phone": "123",
            }
        )
        self.assertEqual(response.status_code, 200)
        profile = DonorProfile.objects.get(user=self.donor)
        self.assertNotEqual(profile.age, 200)
        self.assertNotEqual(profile.blood_group, "INVALID")

    def test_underage_donor_profile_is_rejected(self):
        self.client.force_login(self.donor)
        response = self.client.post(
            reverse("donor_profile"),
            {
                "blood_group": "A+",
                "age": 16,  # Below 18
            }
        )
        self.assertEqual(response.status_code, 200)
        profile = DonorProfile.objects.get(user=self.donor)
        self.assertNotEqual(profile.age, 16)

    def test_unauthenticated_user_cannot_access_donor_profile(self):
        response = self.client.get(reverse("donor_profile"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login", response.url)



class BloodExpiryTrackingTests(TestCase):
    """
    BB-F-018: Blood Expiry Tracking (TC-INV-05)
    The system shall store and display expiry information for blood units
    where such information is recorded.
    """
    def setUp(self):
        self.donor = User.objects.create_user(
            username="expiry_donor",
            password="password123"
        )
        self.reviewer = User.objects.create_user(
            username="expiry_reviewer",
            password="password123",
            is_staff=True
        )

    def test_donation_auto_calculates_expiry_date_42_days_from_donation(self):
        donation = Donation.objects.create(
            donor=self.donor,
            blood_group="O+",
            donation_date=date.today(),
            units=2
        )
        self.assertIsNotNone(donation.expiry_date)
        self.assertEqual(
            donation.expiry_date,
            date.today() + timedelta(days=42)
        )

    def test_donation_with_explicit_expiry_date_preserves_custom_date(self):
        custom_expiry = date.today() + timedelta(days=30)
        donation = Donation.objects.create(
            donor=self.donor,
            blood_group="B+",
            donation_date=date.today(),
            expiry_date=custom_expiry,
            units=1
        )
        self.assertEqual(donation.expiry_date, custom_expiry)

    def test_donation_form_rejects_expiry_date_earlier_than_donation_date(self):
        self.client.force_login(self.donor)
        response = self.client.post(
            reverse("submit_donation"),
            {
                "blood_group": "AB+",
                "donation_date": date.today().isoformat(),
                "expiry_date": (date.today() - timedelta(days=1)).isoformat(),
                "units": 1,
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Donation.objects.filter(blood_group="AB+").exists()
        )

    def test_approving_donation_updates_stock_record_with_expiry_info(self):
        expiry_date = date.today() + timedelta(days=35)
        donation = Donation.objects.create(
            donor=self.donor,
            blood_group="A-",
            donation_date=date.today(),
            expiry_date=expiry_date,
            units=3
        )
        self.assertTrue(
            review_donation(donation.id, self.reviewer, "approve")
        )

        inventory = BloodInventory.objects.get(blood_group="A-")
        self.assertEqual(inventory.units, 3)
        self.assertEqual(inventory.expiry_date, expiry_date)
        self.assertEqual(inventory.nearest_expiry, expiry_date)

    def test_blood_availability_displays_associated_expiry_date(self):
        expiry_date = date.today() + timedelta(days=25)
        BloodInventory.objects.create(
            blood_group="O-",
            units=4,
            expiry_date=expiry_date
        )

        response = self.client.get(reverse("blood_availability"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, expiry_date.strftime("%Y-%m-%d"))
        self.assertContains(response, "Earliest Expiry:")

        data = {item["blood_group"]: item for item in response.context["blood_groups"]}
        self.assertEqual(data["O-"]["expiry_date"], expiry_date)


class PerformanceRequirementsTests(TestCase):
    """
    BB-NF-001: Performance Requirements & TC-PERF-01 Test Suite
    Verifies that:
    1. Normal page requests and routine database operations respond within 3 seconds.
    2. At least 95% of measured common requests complete within 3 seconds.
    3. Common operations (login, blood availability, dashboards, history) execute without delays.
    4. Database query counts are bounded and eliminate N+1 query bottlenecks.
    5. Performance timing headers (X-Response-Time, Server-Timing) are present.
    6. Performance settings (caching, connection persistence) are properly configured.
    """

    def setUp(self):
        self.password = "StrongPass123!"
        self.donor_user = User.objects.create_user(
            username="perf_donor",
            password=self.password
        )
        self.patient_user = User.objects.create_user(
            username="perf_patient",
            password=self.password
        )
        self.staff_user = User.objects.create_user(
            username="perf_staff",
            password=self.password,
            is_staff=True
        )

        for bg, _ in Donation.BLOOD_GROUPS:
            BloodInventory.objects.create(
                blood_group=bg,
                units=10,
                expiry_date=date.today() + timedelta(days=30)
            )

        for i in range(15):
            Donation.objects.create(
                donor=self.donor_user,
                blood_group="O+",
                donation_date=date.today(),
                units=1,
                status="Pending"
            )

    def test_response_timing_headers_injected_by_middleware(self):
        response = self.client.get(reverse("blood_availability"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("X-Response-Time", response.headers)
        self.assertIn("X-DB-Queries", response.headers)
        self.assertIn("Server-Timing", response.headers)
        self.assertTrue(response.headers["X-Response-Time"].endswith("s"))
        self.assertTrue(response.headers["X-DB-Queries"].isdigit())
        self.assertIn("sql;dur=", response.headers["Server-Timing"])

    def test_blood_availability_response_time_under_sla(self):
        start = time.perf_counter()
        response = self.client.get(reverse("blood_availability"))
        elapsed = time.perf_counter() - start

        self.assertEqual(response.status_code, 200)
        self.assertLess(elapsed, 3.0, f"Blood availability response time {elapsed}s exceeded 3s target")

    def test_login_response_time_under_sla(self):
        start = time.perf_counter()
        response = self.client.get(reverse("login"))
        elapsed_get = time.perf_counter() - start
        self.assertEqual(response.status_code, 200)
        self.assertLess(elapsed_get, 3.0, f"Login GET response time {elapsed_get}s exceeded 3s target")

        start = time.perf_counter()
        post_response = self.client.post(
            reverse("login"),
            {"username": "perf_donor", "password": self.password}
        )
        elapsed_post = time.perf_counter() - start
        self.assertIn(post_response.status_code, (200, 302))
        self.assertLess(elapsed_post, 3.0, f"Login POST response time {elapsed_post}s exceeded 3s target")

    def test_staff_donation_dashboard_response_time_under_sla(self):
        self.client.force_login(self.staff_user)
        start = time.perf_counter()
        response = self.client.get(reverse("manage_donations"))
        elapsed = time.perf_counter() - start

        self.assertEqual(response.status_code, 200)
        self.assertLess(elapsed, 3.0, f"Manage donations response time {elapsed}s exceeded 3s target")

    def test_donation_and_request_history_response_times_under_sla(self):
        self.client.force_login(self.donor_user)
        start = time.perf_counter()
        response_don = self.client.get(reverse("donation_history"))
        elapsed_don = time.perf_counter() - start

        self.assertEqual(response_don.status_code, 200)
        self.assertLess(elapsed_don, 3.0, f"Donation history response time {elapsed_don}s exceeded 3s target")

        self.client.force_login(self.patient_user)
        start = time.perf_counter()
        response_req = self.client.get(reverse("blood_request_history"))
        elapsed_req = time.perf_counter() - start

        self.assertEqual(response_req.status_code, 200)
        self.assertLess(elapsed_req, 3.0, f"Request history response time {elapsed_req}s exceeded 3s target")

    def test_ninety_five_percent_of_measured_requests_under_target(self):
        urls_to_test = [
            reverse("blood_availability"),
            reverse("login"),
            reverse("register"),
        ]

        latencies = []
        for _ in range(15):
            for url in urls_to_test:
                start = time.perf_counter()
                res = self.client.get(url)
                duration = time.perf_counter() - start
                self.assertEqual(res.status_code, 200)
                latencies.append(duration)

        total_requests = len(latencies)
        within_sla = [t for t in latencies if t < 3.0]
        compliance_ratio = len(within_sla) / total_requests

        self.assertGreaterEqual(
            compliance_ratio,
            0.95,
            f"Expected at least 95% within 3s, achieved {compliance_ratio * 100:.1f}% ({len(within_sla)}/{total_requests})"
        )

    def test_blood_availability_query_count_prevents_n_plus_one(self):
        with self.assertNumQueries(2):
            response = self.client.get(reverse("blood_availability"))
            self.assertEqual(response.status_code, 200)

    def test_manage_donations_pagination_bounds_display_count(self):
        for i in range(20):
            Donation.objects.create(
                donor=self.donor_user,
                blood_group="AB+",
                donation_date=date.today(),
                units=1
            )

        self.client.force_login(self.staff_user)
        response = self.client.get(reverse("manage_donations"))
        self.assertEqual(response.status_code, 200)
        page_obj = response.context["page_obj"]
        self.assertEqual(len(page_obj), 25)
        self.assertTrue(page_obj.has_next())

    def test_performance_configuration_settings(self):
        self.assertIn("default", settings.CACHES)
        self.assertEqual(settings.DATABASES["default"].get("CONN_MAX_AGE"), 600)
        self.assertIn("django.middleware.gzip.GZipMiddleware", settings.MIDDLEWARE)
        self.assertIn("blood.middleware.PerformanceTimingMiddleware", settings.MIDDLEWARE)

    def test_admin_classes_have_list_select_related(self):
        from .admin import BloodRequestAdmin, PatientProfileAdmin, DonorProfileAdmin
        self.assertEqual(DonationAdmin.list_select_related, ("donor", "reviewed_by"))
        self.assertEqual(BloodRequestAdmin.list_select_related, ("patient",))
        self.assertEqual(PatientProfileAdmin.list_select_related, ("user",))
        self.assertEqual(DonorProfileAdmin.list_select_related, ("user",))


class BloodRequestReviewServiceTests(TestCase):
    def setUp(self):
        self.patient = User.objects.create_user(username="request_patient")
        self.reviewer = User.objects.create_user(
            username="request_reviewer",
            is_staff=True,
        )

    def create_request(self, units=2, blood_group="O+"):
        return BloodRequest.objects.create(
            patient=self.patient,
            blood_group=blood_group,
            units=units,
            needed_by_date=date.today() + timedelta(days=5),
            notes="Urgent surgery support",
        )

    def test_approving_pending_request_deducts_inventory(self):
        request = self.create_request(units=3)
        BloodInventory.objects.create(blood_group="O+", units=10)

        self.assertTrue(
            review_blood_request(request.id, self.reviewer, "approve")
        )

        request.refresh_from_db()
        self.assertEqual(request.status, "Approved")
        self.assertEqual(BloodInventory.objects.get(blood_group="O+").units, 7)

    def test_rejecting_pending_request_does_not_modify_inventory(self):
        request = self.create_request(units=3)
        BloodInventory.objects.create(blood_group="O+", units=10)

        self.assertTrue(
            review_blood_request(request.id, self.reviewer, "reject")
        )

        request.refresh_from_db()
        self.assertEqual(request.status, "Rejected")
        self.assertEqual(BloodInventory.objects.get(blood_group="O+").units, 10)

    def test_repeated_review_of_processed_request_is_rejected(self):
        request = self.create_request(units=2)
        BloodInventory.objects.create(blood_group="O+", units=5)

        self.assertTrue(
            review_blood_request(request.id, self.reviewer, "approve")
        )
        self.assertFalse(
            review_blood_request(request.id, self.reviewer, "reject")
        )
        self.assertFalse(
            review_blood_request(request.id, self.reviewer, "approve")
        )

        request.refresh_from_db()
        self.assertEqual(request.status, "Approved")
        self.assertEqual(BloodInventory.objects.get(blood_group="O+").units, 3)

    def test_approval_requires_sufficient_stock(self):
        request = self.create_request(units=5)
        BloodInventory.objects.create(blood_group="O+", units=3)

        self.assertFalse(
            review_blood_request(request.id, self.reviewer, "approve")
        )

        request.refresh_from_db()
        self.assertEqual(request.status, "Pending")
        self.assertEqual(BloodInventory.objects.get(blood_group="O+").units, 3)


class BloodRequestReviewWorkflowTests(TestCase):
    def setUp(self):
        self.patient = User.objects.create_user(username="workflow_patient")
        self.reviewer = User.objects.create_user(username="workflow_reviewer", is_staff=True)
        self.client.force_login(self.reviewer)
        self.request = BloodRequest.objects.create(
            patient=self.patient,
            blood_group="A+",
            units=2,
            needed_by_date=date.today() + timedelta(days=4),
            notes="Routine check-up",
        )

    def test_staff_can_review_pending_requests(self):
        BloodInventory.objects.create(blood_group="A+", units=5)

        response = self.client.post(
            reverse("review_blood_request", kwargs={"request_id": self.request.id}),
            {"action": "approve"},
        )

        self.assertRedirects(response, reverse("manage_blood_requests"))
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, "Approved")
        self.assertEqual(BloodInventory.objects.get(blood_group="A+").units, 3)

    def test_staff_review_rejects_invalid_and_insufficient_stock_actions(self):
        invalid_response = self.client.post(
            reverse("review_blood_request", kwargs={"request_id": self.request.id}),
            {"action": "invalid"},
        )

        self.assertRedirects(invalid_response, reverse("manage_blood_requests"))
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, "Pending")

        BloodInventory.objects.create(blood_group="A+", units=1)
        insufficient_response = self.client.post(
            reverse("review_blood_request", kwargs={"request_id": self.request.id}),
            {"action": "approve"},
        )

        self.assertRedirects(insufficient_response, reverse("manage_blood_requests"))
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, "Pending")
        self.assertEqual(BloodInventory.objects.get(blood_group="A+").units, 1)

    def test_review_page_lists_only_pending_requests(self):
        second_pending = BloodRequest.objects.create(
            patient=self.patient,
            blood_group="B+",
            units=1,
            needed_by_date=date.today() + timedelta(days=2),
            notes="Another request",
            status="Pending",
        )
        BloodRequest.objects.create(
            patient=self.patient,
            blood_group="AB+",
            units=1,
            needed_by_date=date.today() + timedelta(days=1),
            notes="Already handled",
            status="Approved",
        )

        response = self.client.get(reverse("manage_blood_requests"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["blood_requests"]), [self.request, second_pending])

    def test_non_staff_user_cannot_access_review_page(self):
        self.client.logout()
        user = User.objects.create_user(username="plain_user", password="pass123")
        self.client.force_login(user)

        review_page_response = self.client.get(reverse("manage_blood_requests"))
        review_action_response = self.client.post(
            reverse("review_blood_request", kwargs={"request_id": self.request.id}),
            {"action": "approve"},
        )

        self.assertEqual(review_page_response.status_code, 302)
        self.assertIn("/admin/login/", review_page_response.url)
        self.assertEqual(review_action_response.status_code, 302)
        self.assertIn("/admin/login/", review_action_response.url)


class BloodInventoryUpdateTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="inventory_admin", password="password123", is_staff=True)
        self.client.force_login(self.staff)

    def test_staff_can_update_inventory_for_a_blood_group(self):
        BloodInventory.objects.create(blood_group="A+", units=2)

        response = self.client.post(
            reverse("update_inventory"),
            {"blood_group": "A+", "units": 12},
        )

        self.assertEqual(response.status_code, 302)
        inventory = BloodInventory.objects.get(blood_group="A+")
        self.assertEqual(inventory.units, 12)

    def test_invalid_inventory_values_are_rejected(self):
        response = self.client.post(
            reverse("update_inventory"),
            {"blood_group": "A+", "units": -1},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ensure this value is greater than or equal to 0.")
        self.assertFalse(BloodInventory.objects.filter(blood_group="A+").exists())

    def test_non_staff_cannot_access_inventory_update_page(self):
        self.client.logout()
        user = User.objects.create_user(username="regular_user", password="password123")
        self.client.force_login(user)

        response = self.client.get(reverse("update_inventory"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_inventory_update_uses_existing_blood_group_choices(self):
        response = self.client.get(reverse("update_inventory"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="blood_group"')
        self.assertContains(response, 'A+')
        self.assertContains(response, 'O-')


class AdminDashboardTests(TestCase):
    """
    BB-F-016: Administrator Dashboard (TC-ADM-01, BB-SR-003)
    Verifies staff-only access control, aggregated donor/patient metrics,
    blood request and donation status breakdowns, inventory stock counts,
    and staff navigation links.
    """
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="dashboard_staff",
            password="staffpassword123",
            is_staff=True,
        )
        self.regular_user = User.objects.create_user(
            username="regular_dashboard_user",
            password="regularpassword123",
            is_staff=False,
        )
        self.client.force_login(self.staff_user)

    def test_non_staff_user_is_redirected(self):
        self.client.logout()
        self.client.force_login(self.regular_user)
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)

    def test_unauthenticated_user_is_redirected(self):
        self.client.logout()
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)

    def test_dashboard_shows_accurate_donor_and_patient_counts(self):
        u1 = User.objects.create_user(username="donor1", password="pw1")
        u2 = User.objects.create_user(username="donor2", password="pw2")
        u3 = User.objects.create_user(username="patient1", password="pw3")
        u4 = User.objects.create_user(username="dual_user", password="pw4")

        DonorProfile.objects.create(user=u1, blood_group="A+")
        DonorProfile.objects.create(user=u2, blood_group="B+")
        DonorProfile.objects.create(user=u4, blood_group="O+")

        PatientProfile.objects.create(user=u3, blood_group="AB+")
        PatientProfile.objects.create(user=u4, blood_group="O+")

        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['donor_count'], 3)
        self.assertEqual(response.context['patient_count'], 2)
        self.assertContains(response, '3')
        self.assertContains(response, '2')

    def test_dashboard_shows_accurate_blood_requests_by_status(self):
        patient = User.objects.create_user(username="patient_req", password="pw")
        today = date.today()
        BloodRequest.objects.create(patient=patient, blood_group="A+", units=2, needed_by_date=today, status="Pending")
        BloodRequest.objects.create(patient=patient, blood_group="B+", units=1, needed_by_date=today, status="Pending")
        BloodRequest.objects.create(patient=patient, blood_group="O+", units=3, needed_by_date=today, status="Approved")
        BloodRequest.objects.create(patient=patient, blood_group="AB-", units=1, needed_by_date=today, status="Rejected")

        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['request_counts']['total'], 4)
        self.assertEqual(response.context['request_counts']['pending'], 2)
        self.assertEqual(response.context['request_counts']['approved'], 1)
        self.assertEqual(response.context['request_counts']['rejected'], 1)

    def test_dashboard_shows_accurate_donations_by_status(self):
        donor = User.objects.create_user(username="donor_don", password="pw")
        today = date.today()
        Donation.objects.create(donor=donor, blood_group="A+", units=1, donation_date=today, status="Pending")
        Donation.objects.create(donor=donor, blood_group="A-", units=2, donation_date=today, status="Approved")
        Donation.objects.create(donor=donor, blood_group="B+", units=1, donation_date=today, status="Approved")
        Donation.objects.create(donor=donor, blood_group="O-", units=1, donation_date=today, status="Rejected")

        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['donation_counts']['total'], 4)
        self.assertEqual(response.context['donation_counts']['pending'], 1)
        self.assertEqual(response.context['donation_counts']['approved'], 2)
        self.assertEqual(response.context['donation_counts']['rejected'], 1)

    def test_dashboard_shows_accurate_stock_per_blood_group_and_total(self):
        BloodInventory.objects.create(blood_group="A+", units=10)
        BloodInventory.objects.create(blood_group="B+", units=5)
        BloodInventory.objects.create(blood_group="O-", units=8)

        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_stock_units'], 23)

        stock_dict = {item['blood_group']: item['units'] for item in response.context['stock_by_group']}
        self.assertEqual(len(stock_dict), 8)
        self.assertEqual(stock_dict['A+'], 10)
        self.assertEqual(stock_dict['B+'], 5)
        self.assertEqual(stock_dict['O-'], 8)
        self.assertEqual(stock_dict['AB+'], 0)

    def test_dashboard_links_to_existing_staff_pages(self):
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('manage_donations'))
        self.assertContains(response, reverse('manage_blood_requests'))
        self.assertContains(response, reverse('update_inventory'))

    def test_staff_navbar_contains_dashboard_link(self):
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('admin_dashboard'))

        self.client.logout()
        self.client.force_login(self.regular_user)
        user_response = self.client.get(reverse('blood_availability'))
        self.assertNotContains(user_response, reverse('admin_dashboard'))


class UserManagementTests(TestCase):
    """
    BB-F-017: User Management (TC-ADM-02, BB-SR-003)
    Verifies staff-only user management interface, multi-field search across
    user and profile attributes, activate/deactivate account actions,
    protection guards for self and superuser accounts, and login prevention
    for deactivated users.
    """
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="staff_admin",
            password="adminpassword123",
            email="staff@example.com",
            is_staff=True,
        )
        self.superuser = User.objects.create_superuser(
            username="super_admin",
            password="superpassword123",
            email="super@example.com",
        )
        self.target_user = User.objects.create_user(
            username="john_doe",
            password="password123",
            email="john@example.com",
            first_name="John",
            last_name="Doe",
        )
        self.client.force_login(self.staff_user)

    def test_non_staff_user_cannot_access_user_list(self):
        self.client.logout()
        self.client.force_login(self.target_user)
        response = self.client.get(reverse('user_management'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)

    def test_unauthenticated_user_cannot_access_user_list(self):
        self.client.logout()
        response = self.client.get(reverse('user_management'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)

    def test_staff_can_view_user_list_with_profiles(self):
        DonorProfile.objects.create(
            user=self.target_user,
            blood_group="O+",
            age=30,
            contact_phone="1234567890",
        )
        PatientProfile.objects.create(
            user=self.target_user,
            blood_group="O+",
            disease="Anemia",
            contact_phone="1234567890",
        )

        response = self.client.get(reverse('user_management'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "john_doe")
        self.assertContains(response, "john@example.com")
        self.assertContains(response, "O+")
        self.assertContains(response, "1234567890")
        self.assertContains(response, "Anemia")

    def test_search_users_by_username_and_email(self):
        User.objects.create_user(username="alice", email="alice@test.org")
        User.objects.create_user(username="bob", email="bob@sample.net")

        response = self.client.get(reverse('user_management'), {'q': 'alice'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "alice")
        self.assertNotContains(response, "bob@sample.net")

    def test_search_users_by_profile_attributes(self):
        user_donor = User.objects.create_user(username="donor_only", email="donor@test.org")
        DonorProfile.objects.create(user=user_donor, blood_group="AB-", contact_phone="9988776655")

        user_patient = User.objects.create_user(username="patient_only", email="patient@test.org")
        PatientProfile.objects.create(user=user_patient, blood_group="B-", contact_phone="1122334455")

        response = self.client.get(reverse('user_management'), {'q': '9988776655'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "donor_only")
        self.assertNotContains(response, "patient_only")

    def test_toggle_endpoint_rejects_get_requests(self):
        response = self.client.get(
            reverse('toggle_user_active', kwargs={'user_id': self.target_user.id})
        )
        self.assertEqual(response.status_code, 405)

    def test_non_staff_cannot_toggle_user_status(self):
        self.client.logout()
        self.client.force_login(self.target_user)
        response = self.client.post(
            reverse('toggle_user_active', kwargs={'user_id': self.target_user.id}),
            {'action': 'deactivate'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)
        self.target_user.refresh_from_db()
        self.assertTrue(self.target_user.is_active)

    def test_staff_can_deactivate_and_activate_user(self):
        # Deactivate
        response = self.client.post(
            reverse('toggle_user_active', kwargs={'user_id': self.target_user.id}),
            {'action': 'deactivate'},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.target_user.refresh_from_db()
        self.assertFalse(self.target_user.is_active)
        self.assertContains(response, "deactivated")

        # Activate
        response = self.client.post(
            reverse('toggle_user_active', kwargs={'user_id': self.target_user.id}),
            {'action': 'activate'},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.target_user.refresh_from_db()
        self.assertTrue(self.target_user.is_active)
        self.assertContains(response, "activated")

    def test_self_deactivation_is_blocked_by_guard(self):
        response = self.client.post(
            reverse('toggle_user_active', kwargs={'user_id': self.staff_user.id}),
            {'action': 'deactivate'},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.staff_user.refresh_from_db()
        self.assertTrue(self.staff_user.is_active)
        self.assertContains(response, "You cannot deactivate your own account.")

    def test_superuser_deactivation_is_blocked_by_guard(self):
        response = self.client.post(
            reverse('toggle_user_active', kwargs={'user_id': self.superuser.id}),
            {'action': 'deactivate'},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_active)
        self.assertContains(response, "Superuser accounts cannot be deactivated.")

    def test_deactivated_user_cannot_log_in(self):
        self.target_user.is_active = False
        self.target_user.save()

        self.client.logout()
        response = self.client.post(
            reverse('login'),
            {'username': 'john_doe', 'password': 'password123'},
        )
        # Login should fail and re-render login form with error
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['user'].is_authenticated)

    def test_staff_navbar_contains_user_management_link(self):
        response = self.client.get(reverse('user_management'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('user_management'))

        self.client.logout()
        self.client.force_login(self.target_user)
        user_response = self.client.get(reverse('blood_availability'))
        self.assertNotContains(user_response, reverse('user_management'))



