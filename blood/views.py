from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Min, Count, Sum, Q
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST

from .forms import DonationForm, BloodRequestForm, PatientProfileForm, DonorProfileForm, UserRegisterForm, BloodInventoryUpdateForm
from .models import Donation, BloodInventory, BloodRequest, PatientProfile, DonorProfile
from .services import review_donation as process_donation_review
from .services import review_blood_request as process_blood_request_review
from .services import update_inventory_stock


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
    donation_list = Donation.objects.select_related(
        'donor', 'reviewed_by'
    ).order_by('-created_at')

    paginator = Paginator(donation_list, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        'blood/manage_donations.html',
        {
            'donations': page_obj,
            'page_obj': page_obj,
        }
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


@staff_member_required
def manage_blood_requests(request):
    """Display pending blood requests for administrative review."""
    blood_requests = BloodRequest.objects.select_related('patient').filter(
        status='Pending'
    ).order_by('-created_at')
    return render(
        request,
        'blood/manage_blood_requests.html',
        {
            'blood_requests': blood_requests,
        }
    )


@staff_member_required
@require_POST
def review_blood_request(request, request_id):
    action = request.POST.get('action')

    if action not in ('approve', 'reject'):
        messages.error(request, 'Invalid review action.')
        return redirect('manage_blood_requests')

    completed = process_blood_request_review(
        request_id,
        request.user,
        action,
    )

    if completed:
        messages.success(request, f'Blood request {action}d successfully.')
    else:
        blood_request = BloodRequest.objects.filter(pk=request_id).first()
        if blood_request and blood_request.status != 'Pending':
            messages.warning(request, 'Blood request has already been processed.')
        elif blood_request and blood_request.blood_group and blood_request.units:
            messages.warning(request, 'Insufficient blood stock to approve this request.')
        else:
            messages.warning(request, 'Blood request not found or already processed.')

    return redirect('manage_blood_requests')


def view_blood_availability(request):
    """
    BB-F-011: View Blood Availability
    BB-F-018: Blood Expiry Tracking (TC-INV-05)
    BB-NF-001: Performance Optimization (TC-PERF-01)
    Displays current available blood stock by blood group along with recorded expiry information.
    Ensures all 8 standard blood groups are displayed, reflecting inventory records.
    Optimized with single batched aggregation query to prevent N+1 queries.
    This presentation is strictly read-only for users.
    """
    inventory_records = {
        item.blood_group: item
        for item in BloodInventory.objects.all()
    }

    # Batch compute earliest expiry for groups lacking direct inventory expiry in a single query
    earliest_expiries = {
        row['blood_group']: row['min_expiry']
        for row in Donation.objects.filter(
            status='Approved',
            expiry_date__isnull=False
        ).values('blood_group').annotate(min_expiry=Min('expiry_date'))
    }

    blood_groups_data = []
    total_units = 0
    for group, _ in Donation.BLOOD_GROUPS:
        item = inventory_records.get(group)
        units = item.units if item else 0
        if item and item.expiry_date:
            expiry_date = item.expiry_date
        else:
            expiry_date = earliest_expiries.get(group)
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


@staff_member_required
def update_inventory(request):
    """Allow staff to maintain per-blood-group inventory counts."""
    inventory_records = BloodInventory.objects.order_by('blood_group')

    if request.method == 'POST':
        form = BloodInventoryUpdateForm(request.POST)
        if form.is_valid():
            blood_group = form.cleaned_data['blood_group']
            units = form.cleaned_data['units']
            try:
                update_inventory_stock(blood_group, units)
                messages.success(request, f'Inventory updated for {blood_group}.')
            except ValueError as exc:
                messages.error(request, str(exc))
            return redirect('update_inventory')
    else:
        form = BloodInventoryUpdateForm()

    return render(
        request,
        'blood/update_inventory.html',
        {
            'form': form,
            'inventory_records': inventory_records,
        }
    )


@staff_member_required
def admin_dashboard(request):
    """
    BB-F-016: Administrator Dashboard (TC-ADM-01, BB-SR-003)
    Staff-only dashboard providing high-level operational metrics:
    - Registered donors and patients counts
    - Blood requests by status (Pending, Approved, Rejected)
    - Donations by status (Pending, Approved, Rejected)
    - Current inventory stock by blood group and total available units
    - Direct navigation links to administrative review and inventory workflows

    Donor and patient counts:
    Donors are counted as registered users with an associated DonorProfile
    (DonorProfile.objects.count()). Patients are counted as registered users
    with an associated PatientProfile (PatientProfile.objects.count()).
    Because every account may use both donor and patient functions without a
    mutually exclusive role field, counts reflect active profile registrations.
    """
    donor_count = DonorProfile.objects.count()
    patient_count = PatientProfile.objects.count()

    request_aggregates = BloodRequest.objects.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status='Pending')),
        approved=Count('id', filter=Q(status='Approved')),
        rejected=Count('id', filter=Q(status='Rejected')),
    )

    donation_aggregates = Donation.objects.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status='Pending')),
        approved=Count('id', filter=Q(status='Approved')),
        rejected=Count('id', filter=Q(status='Rejected')),
    )

    inventory_records = {
        item['blood_group']: item['units']
        for item in BloodInventory.objects.values('blood_group', 'units')
    }

    stock_by_group = []
    for group, _ in Donation.BLOOD_GROUPS:
        stock_by_group.append({
            'blood_group': group,
            'units': inventory_records.get(group, 0),
        })

    total_stock_units = BloodInventory.objects.aggregate(total=Sum('units'))['total'] or 0

    return render(
        request,
        'blood/admin_dashboard.html',
        {
            'donor_count': donor_count,
            'patient_count': patient_count,
            'request_counts': request_aggregates,
            'donation_counts': donation_aggregates,
            'stock_by_group': stock_by_group,
            'total_stock_units': total_stock_units,
        }
    )


@staff_member_required
def user_management(request):
    """
    BB-F-017: User Management (TC-ADM-02, BB-SR-003)
    Staff-only view to list and search registered users along with their
    donor and patient profile details.
    """
    search_query = request.GET.get('q', '').strip()
    users_qs = User.objects.select_related(
        'donor_profile', 'patient_profile'
    ).order_by('-date_joined')

    if search_query:
        users_qs = users_qs.filter(
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(donor_profile__blood_group__icontains=search_query) |
            Q(donor_profile__contact_phone__icontains=search_query) |
            Q(patient_profile__blood_group__icontains=search_query) |
            Q(patient_profile__contact_phone__icontains=search_query)
        ).distinct()

    paginator = Paginator(users_qs, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        'blood/user_management.html',
        {
            'page_obj': page_obj,
            'users': page_obj,
            'search_query': search_query,
            'total_users': paginator.count,
        }
    )


