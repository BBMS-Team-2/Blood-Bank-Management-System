from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST

from .forms import DonationForm, BloodRequestForm, PatientProfileForm, DonorProfileForm, UserRegisterForm
from .models import Donation, BloodInventory, BloodRequest, PatientProfile, DonorProfile
from .services import review_donation as process_donation_review


@login_required
def submit_donation(request):
    if request.method == 'POST':
        form = DonationForm(request.POST)
        if form.is_valid():
            donation = form.save(commit=False)
            donation.donor = request.user
            donation.status = 'Pending'
            donation.save()

            messages.success(request, 'Donation submitted for review.')
            return redirect('submit_donation')
    else:
        form = DonationForm()

    return render(
        request,
        'blood/submit_donation.html',
        {'form': form}
    )


@login_required
def submit_blood_request(request):
    if request.method == 'POST':
        form = BloodRequestForm(request.POST)
        if form.is_valid():
            blood_request = form.save(commit=False)
            blood_request.patient = request.user
            blood_request.status = 'Pending'
            blood_request.save()

            messages.success(request, 'Blood request submitted successfully.')
            return redirect('submit_blood_request')
    else:
        form = BloodRequestForm()

    return render(
        request,
        'blood/submit_blood_request.html',
        {'form': form}
    )


@staff_member_required
def manage_donations(request):
    donations = Donation.objects.select_related(
        'donor', 'reviewed_by'
    ).order_by('-created_at')

    return render(
        request,
        'blood/manage_donations.html',
        {'donations': donations}
    )


@staff_member_required
@require_POST
def review_donation(request, donation_id):
    action = request.POST.get('action')

    if action not in ('approve', 'reject'):
        messages.error(request, 'Invalid review action.')
        return redirect('manage_donations')

    completed = process_donation_review(
        donation_id,
        request.user,
        action,
    )

    if completed:
        messages.success(request, f'Donation {action}d successfully.')
    else:
        messages.warning(
            request,
            'Donation not found or already reviewed.'
        )

    return redirect('manage_donations')


def view_blood_availability(request):
    """
    BB-F-011: View Blood Availability
    BB-F-018: Blood Expiry Tracking (TC-INV-05)
    Displays current available blood stock by blood group along with recorded expiry information.
    Ensures all 8 standard blood groups are displayed, reflecting inventory records.
    This presentation is strictly read-only for users.
    """
    inventory_records = {
        item.blood_group: item
        for item in BloodInventory.objects.all()
    }

    blood_groups_data = []
    total_units = 0
    for group, _ in Donation.BLOOD_GROUPS:
        item = inventory_records.get(group)
        units = item.units if item else 0
        expiry_date = item.nearest_expiry if item else None
        total_units += units
        if units == 0:
            status = 'Out of Stock'
            status_class = 'danger'
        elif units < 5:
            status = 'Low Stock'
            status_class = 'warning'
        else:
            status = 'Available'
            status_class = 'success'

        blood_groups_data.append({
            'blood_group': group,
            'units': units,
            'expiry_date': expiry_date,
            'status': status,
            'status_class': status_class,
        })

    return render(
        request,
        'blood/blood_availability.html',
        {
            'blood_groups': blood_groups_data,
            'total_units': total_units,
        }
    )


@login_required
def donation_history(request):
    """
    BB-F-007: Donation History (BB-SR-003)
    Allows authenticated donors to view their past donation records and review status.
    Ensures complete isolation so donors can only view their own records.
    """
    donations = Donation.objects.filter(
        donor=request.user
    ).select_related('reviewed_by').order_by('-donation_date', '-created_at')

    return render(
        request,
        'blood/donation_history.html',
        {'donations': donations}
    )


@login_required
def blood_request_history(request):
    """
    BB-F-015: Blood Request History (BB-SR-003)
    Allows authenticated patients to view the status and history of their own blood requests.
    Enforces privacy isolation across patients.
    """
    blood_requests = BloodRequest.objects.filter(
        patient=request.user
    ).order_by('-needed_by_date', '-created_at')

    return render(
        request,
        'blood/blood_request_history.html',
        {'blood_requests': blood_requests}
    )


@login_required
def patient_profile(request):
    """
    BB-F-008: Patient Profile Management
    Allows authenticated patients to view and update their profile details.
    """
    profile, _ = PatientProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        form = PatientProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your patient profile has been updated successfully.')
            return redirect('patient_profile')
    else:
        form = PatientProfileForm(instance=profile)

    return render(
        request,
        'blood/patient_profile.html',
        {
            'form': form,
            'profile': profile,
        }
    )


@login_required
def donor_profile(request):
    """
    BB-F-004: Donor Profile Management
    Allows authenticated donors to view and update their profile details.
    """
    profile, _ = DonorProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        form = DonorProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your donor profile has been updated successfully.')
            return redirect('donor_profile')
    else:
        form = DonorProfileForm(instance=profile)

    return render(
        request,
        'blood/donor_profile.html',
        {
            'form': form,
            'profile': profile,
        }
    )


def register_view(request):
    """
    BB-NF-003, BB-F-001: User Registration
    Creates account using secure password hashing and input validation.
    """
    if request.user.is_authenticated:
        return redirect('blood_availability')

    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'Account created for {user.username}. You may now log in.')
            return redirect('login')
    else:
        form = UserRegisterForm()

    return render(request, 'blood/register.html', {'form': form})


def login_view(request):
    """
    BB-NF-003, BB-F-002: User Login
    Authenticates registered users securely; rejects invalid credentials without leaking details.
    """
    if request.user.is_authenticated:
        return redirect('blood_availability')

    next_url = request.GET.get('next') or request.POST.get('next') or 'blood_availability'

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)
            messages.success(request, f'Welcome back, {user.username}!')
            return redirect(next_url)
    else:
        form = AuthenticationForm(request)

    return render(
        request,
        'blood/login.html',
        {
            'form': form,
            'next': next_url,
        }
    )


def logout_view(request):
    """
    BB-NF-003: User Logout
    Flushes authenticated session safely.
    """
    auth_logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('login')
