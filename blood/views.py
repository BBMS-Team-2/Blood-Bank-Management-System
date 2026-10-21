from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from .forms import DonationForm
from django.contrib.auth.models import User

from django.contrib.admin.views.decorators import staff_member_required
from .models import Donation


@login_required
def submit_donation(request):
    if request.method == 'POST':
        form = DonationForm(request.POST)
        if form.is_valid():
            donation = form.save(commit=False)

            donation.donor = request.user
            donation.status = 'Pending'
            donation.save()

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
    donations = Donation.objects.select_related('donor').order_by('-created_at')

    return render(
        request,
        'blood/manage_donations.html',
        {'donations': donations}
    )
