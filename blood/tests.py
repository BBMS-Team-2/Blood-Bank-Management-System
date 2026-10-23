from datetime import date, timedelta

from django.test import TestCase
from django.conf import settings
from django.contrib.auth.models import User
from django.urls import reverse

from .models import Donation, BloodRequest, BloodInventory, PatientProfile


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


class SecurityAndAuthenticationTests(TestCase):
    """
    BB-NF-003: Security & Password Protection (TC-SEC-01, TC-AUTH-01, BB-SR-001)
    """
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





