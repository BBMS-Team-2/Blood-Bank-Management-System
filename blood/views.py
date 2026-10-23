from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import DonationForm, BloodRequestForm, PatientProfileForm
from .models import Donation, BloodInventory, BloodRequest, PatientProfile


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

    with transaction.atomic():
        donation = get_object_or_404(
            Donation.objects.select_for_update(),
            pk=donation_id
        )

        if donation.status != 'Pending':
            messages.warning(
                request,
                'This donation has already been reviewed.'
            )
            return redirect('manage_donations')

        if action == 'approve':
            # Create the blood-group stock row if it doesn't exist.
            inventory, _ = BloodInventory.objects.get_or_create(
                blood_group=donation.blood_group
            )

            # Atomic increment; avoids overwriting concurrent stock updates.
            BloodInventory.objects.filter(pk=inventory.pk).update(
                units=F('units') + donation.units
            )
            new_status = 'Approved'
        else:
            new_status = 'Rejected'

        # Claim the pending donation exactly once.
        updated = Donation.objects.filter(
            pk=donation.pk,
            status='Pending'
        ).update(
            status=new_status,
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )

        if updated != 1:
            # Raising rolls back the stock increment as well.
            raise RuntimeError(
                'Donation review could not be completed safely.'
            )

    messages.success(
        request,
        f'Donation #{donation_id} {new_status.lower()}.'
    )
    return redirect('manage_donations')


def view_blood_availability(request):
    """
    BB-F-011: View Blood Availability
    Displays current available blood stock by blood group.
    Ensures all 8 standard blood groups are displayed, reflecting inventory records.
    This presentation is strictly read-only for users.
    """
    inventory_map = {
        item.blood_group: item.units
        for item in BloodInventory.objects.all()
    }

    blood_groups_data = []
    total_units = 0
    for group, _ in Donation.BLOOD_GROUPS:
        units = inventory_map.get(group, 0)
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




