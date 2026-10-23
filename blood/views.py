from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST

from .forms import DonationForm
from .models import Donation
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
