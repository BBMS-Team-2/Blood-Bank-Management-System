"""
Seed Demo Data for Blood Bank Management System (BBMS) Viva Presentation.
Run with: python seed_demo_data.py (or .venv/bin/python seed_demo_data.py)
"""
import os
import django
from datetime import date, timedelta
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from blood.models import Donation, BloodInventory, BloodRequest, PatientProfile, DonorProfile


def seed_data():
    print("Clearing existing demo data...")
    BloodRequest.objects.all().delete()
    Donation.objects.all().delete()
    BloodInventory.objects.all().delete()
    PatientProfile.objects.all().delete()
    DonorProfile.objects.all().delete()
    User.objects.filter(username__in=['admin', 'donor_john', 'patient_alice']).delete()

    print("Creating user accounts...")
    # 1. Staff / Superuser Admin
    admin_user = User.objects.create_superuser(
        username='admin',
        email='admin@bbms.org',
        password='AdminPassword123!'
    )
    admin_user.first_name = 'Dr. Sarah'
    admin_user.last_name = 'Venkatesh'
    admin_user.save()

    # 2. Donor Persona
    donor_user = User.objects.create_user(
        username='donor_john',
        email='john.donor@example.com',
        password='DonorPassword123!'
    )
    donor_user.first_name = 'John'
    donor_user.last_name = 'Doe'
    donor_user.save()

    DonorProfile.objects.create(
        user=donor_user,
        blood_group='O+',
        age=28,
        contact_phone='+91-9876543210',
        address='45 Richmond Road, Bengaluru'
    )

    # 3. Patient Persona
    patient_user = User.objects.create_user(
        username='patient_alice',
        email='alice.patient@example.com',
        password='PatientPassword123!'
    )
    patient_user.first_name = 'Alice'
    patient_user.last_name = 'Smith'
    patient_user.save()

    PatientProfile.objects.create(
        user=patient_user,
        blood_group='A+',
        age=34,
        disease='Post-operative Surgery Recovery',
        contact_phone='+91-9876500112',
        address='12 Hospital Road, Bengaluru',
        emergency_contact_name='Robert Smith (Spouse)',
        emergency_contact_phone='+91-9876500119',
        hospital_name='Manipal Hospital, Old Airport Road',
        attending_physician='Dr. Arvind Kumar, MD'
    )

    print("Seeding live blood inventory...")
    # 8 Standard ABO/Rh blood groups with realistic stock & expiries
    inventory_data = [
        ('A+', 15, date.today() + timedelta(days=28)),
        ('A-', 4, date.today() + timedelta(days=14)),
        ('B+', 20, date.today() + timedelta(days=32)),
        ('B-', 3, date.today() + timedelta(days=10)),
        ('AB+', 12, date.today() + timedelta(days=35)),
        ('AB-', 1, date.today() + timedelta(days=7)),   # Critical low stock!
        ('O+', 25, date.today() + timedelta(days=24)),
        ('O-', 2, date.today() + timedelta(days=12)),   # Universal donor low stock!
    ]

    for bg, units, expiry in inventory_data:
        BloodInventory.objects.create(
            blood_group=bg,
            units=units,
            expiry_date=expiry
        )

    print("Seeding donation history records...")
    # Donation 1: 70 days ago (Completed & Approved -> allows donor to be eligible now!)
    Donation.objects.create(
        donor=donor_user,
        blood_group='O+',
        donation_date=date.today() - timedelta(days=70),
        units=1,
        status='Approved',
        expiry_date=date.today() - timedelta(days=70) + timedelta(days=42),
        reviewed_by=admin_user,
        reviewed_at=timezone.now() - timedelta(days=69),
        notes='Routine whole blood donation at Central Blood Bank.'
    )

    # Donation 2: 15 days ago (Approved -> triggers 56-day countdown!)
    Donation.objects.create(
        donor=donor_user,
        blood_group='O+',
        donation_date=date.today() - timedelta(days=15),
        units=1,
        status='Approved',
        expiry_date=date.today() - timedelta(days=15) + timedelta(days=42),
        reviewed_by=admin_user,
        reviewed_at=timezone.now() - timedelta(days=14),
        notes='Voluntary blood drive donation.'
    )

    # Donation 3: Pending review for staff dashboard demonstration
    Donation.objects.create(
        donor=donor_user,
        blood_group='O+',
        donation_date=date.today(),
        units=1,
        status='Pending',
        notes='Walk-in donation awaiting lab testing & approval.'
    )

    print("Seeding blood request history records...")
    # Request 1: Approved (Shows Hospital Ward Pickup Slip!)
    BloodRequest.objects.create(
        patient=patient_user,
        blood_group='A+',
        units=2,
        needed_by_date=date.today() + timedelta(days=1),
        notes='Scheduled orthopedic surgery transfusion.',
        status='Approved',
    )

    # Request 2: Pending (Demonstrates Self-Service Cancellation & Urgency Timer!)
    BloodRequest.objects.create(
        patient=patient_user,
        blood_group='A+',
        units=1,
        needed_by_date=date.today() + timedelta(days=2),
        notes='Emergency standby reserves for ICU patient.',
        status='Pending',
    )

    # Request 3: Rejected
    BloodRequest.objects.create(
        patient=patient_user,
        blood_group='B+',
        units=10,
        needed_by_date=date.today() + timedelta(days=5),
        notes='Excessive reserve request exceeding clinical ceiling.',
        status='Rejected',
    )

    print("\n✅ Successfully seeded demo data!")
    print("\nDemo Accounts Created:")
    print("  1. Admin / Staff : Username: admin         | Password: AdminPassword123!")
    print("  2. Donor         : Username: donor_john    | Password: DonorPassword123!")
    print("  3. Patient       : Username: patient_alice | Password: PatientPassword123!")


if __name__ == '__main__':
    seed_data()
