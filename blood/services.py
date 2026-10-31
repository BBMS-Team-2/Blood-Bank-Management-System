from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import Donation, BloodInventory, BloodRequest


def _normalize_blood_group(blood_group):
    choices = dict(Donation.BLOOD_GROUPS)
    if blood_group not in choices:
        raise ValueError("Invalid blood group.")
    return blood_group


@transaction.atomic
def update_inventory_stock(blood_group, units):
    """Set the exact stock count for a blood group and reject invalid values."""
    normalized_group = _normalize_blood_group(blood_group)

    try:
        units = int(units)
    except (TypeError, ValueError):
        raise ValueError("Inventory units must be a whole number.")

    if units < 0:
        raise ValueError("Inventory units cannot be negative.")

    inventory, _ = BloodInventory.objects.get_or_create(
        blood_group=normalized_group,
        defaults={'units': 0}
    )
    inventory.units = units
    inventory.save(update_fields=['units', 'updated_at'])
    return inventory


@transaction.atomic
def adjust_inventory_stock(blood_group, delta_units):
    """Increase or decrease stock for a blood group, ensuring it never falls below zero."""
    normalized_group = _normalize_blood_group(blood_group)

    try:
        delta_units = int(delta_units)
    except (TypeError, ValueError):
        raise ValueError("Inventory adjustment must be a whole number.")

    inventory, _ = BloodInventory.objects.get_or_create(
        blood_group=normalized_group,
        defaults={'units': 0}
    )

    new_total = inventory.units + delta_units
    if new_total < 0:
        raise ValueError("Inventory cannot go below zero.")

    BloodInventory.objects.filter(pk=inventory.pk).update(
        units=new_total,
        updated_at=timezone.now()
    )
    inventory.refresh_from_db()
    return inventory


@transaction.atomic
def review_donation(donation_id, reviewer, action):
    if action not in ('approve', 'reject'):
        raise ValueError("Action must be 'approve' or 'reject'.")

    try:
        donation = Donation.objects.get(pk=donation_id)
    except Donation.DoesNotExist:
        return False

    new_status = 'Approved' if action == 'approve' else 'Rejected'

    updated = Donation.objects.filter(
        pk=donation_id,
        status='Pending'
    ).update(
        status=new_status,
        reviewed_by=reviewer,
        reviewed_at=timezone.now()
    )

    if updated != 1:
        return False

    if action == 'approve':
        inventory = adjust_inventory_stock(donation.blood_group, donation.units)
        if donation.expiry_date and (not inventory.expiry_date or donation.expiry_date < inventory.expiry_date):
            BloodInventory.objects.filter(pk=inventory.pk).update(expiry_date=donation.expiry_date)

    return True


@transaction.atomic
def review_blood_request(request_id, reviewer, action):
    """Review a pending blood request in a transactional workflow."""
    if action not in ('approve', 'reject'):
        raise ValueError("Action must be 'approve' or 'reject'.")

    try:
        blood_request = BloodRequest.objects.get(pk=request_id)
    except BloodRequest.DoesNotExist:
        return False

    if action == 'reject':
        updated = BloodRequest.objects.filter(
            pk=request_id,
            status='Pending'
        ).update(
            status='Rejected'
        )
        return updated == 1

    inventory = BloodInventory.objects.filter(
        blood_group=blood_request.blood_group
    ).first()

    if inventory is None or inventory.units < blood_request.units:
        return False

    updated = BloodRequest.objects.filter(
        pk=request_id,
        status='Pending'
    ).update(
        status='Approved'
    )

    if updated != 1:
        return False

    adjust_inventory_stock(blood_request.blood_group, -blood_request.units)

    return True


@transaction.atomic
def cancel_blood_request(request_id, user):
    """
    BB-F-015: Blood Request History (BB-SR-003)
    Allows a patient to cancel their own pending blood request.
    Enforces that only pending requests owned by the requesting user can be cancelled.
    """
    updated = BloodRequest.objects.filter(
        pk=request_id,
        patient=user,
        status='Pending'
    ).update(status='Cancelled')
    return updated == 1


@transaction.atomic
def set_user_active_status(target_user_id, acting_user, is_active=None):
    """
    BB-F-017: User Management (TC-ADM-02, BB-SR-003)
    Activates or deactivates a user account with safety guards:
    - Never permitted to deactivate one's own account.
    - Never permitted to deactivate a superuser account.
    - Raises ValueError or PermissionError on violation or invalid input.
    """
    try:
        target_user = User.objects.get(pk=target_user_id)
    except User.DoesNotExist:
        raise ValueError("User not found.")

    if is_active is None:
        new_status = not target_user.is_active
    else:
        new_status = bool(is_active)

    if not new_status:
        if acting_user and target_user.pk == acting_user.pk:
            raise PermissionError("You cannot deactivate your own account.")
        if target_user.is_superuser:
            raise PermissionError("Superuser accounts cannot be deactivated.")

    target_user.is_active = new_status
    target_user.save(update_fields=['is_active'])
    return target_user


# ============================================================================
# BB-NF-003: Authentication Security & Session Protection (TC-SEC-01)
# ============================================================================

MAX_FAILED_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 300  # 5 minutes


def get_client_ip(request):
    """Retrieve client IP address from request headers with fallback."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '127.0.0.1')


def get_login_attempt_cache_key(username, ip_address):
    """Generate consistent cache key for tracking failed login attempts."""
    clean_user = (username or '').strip().lower()
    return f"login_attempts:{clean_user}:{ip_address}"


def check_login_lockout(username, ip_address):
    """
    Check if a user/IP is currently locked out from logging in.
    Returns (is_locked: bool, remaining_seconds: int, attempts: int).
    """
    key = get_login_attempt_cache_key(username, ip_address)
    record = cache.get(key)
    if not record:
        return False, 0, 0

    attempts = record.get('attempts', 0)
    locked_until = record.get('locked_until')
    if locked_until:
        now_ts = timezone.now().timestamp()
        if now_ts < locked_until:
            return True, int(locked_until - now_ts) + 1, attempts
        # Lockout expired
        cache.delete(key)
        return False, 0, 0

    return False, 0, attempts


def record_failed_login_attempt(username, ip_address):
    """
    Increment failed login count for user/IP. Triggers lockout if threshold exceeded.
    Returns (is_locked: bool, remaining_attempts: int, lockout_seconds: int).
    """
    key = get_login_attempt_cache_key(username, ip_address)
    now_ts = timezone.now().timestamp()
    record = cache.get(key) or {'attempts': 0, 'locked_until': None}

    attempts = record['attempts'] + 1
    if attempts >= MAX_FAILED_LOGIN_ATTEMPTS:
        locked_until = now_ts + LOCKOUT_DURATION_SECONDS
        cache.set(key, {'attempts': attempts, 'locked_until': locked_until}, LOCKOUT_DURATION_SECONDS)
        return True, 0, LOCKOUT_DURATION_SECONDS
    else:
        cache.set(key, {'attempts': attempts, 'locked_until': None}, LOCKOUT_DURATION_SECONDS)
        remaining = MAX_FAILED_LOGIN_ATTEMPTS - attempts
        return False, remaining, 0


def clear_failed_login_attempts(username, ip_address):
    """Reset failed login count upon successful authentication."""
    key = get_login_attempt_cache_key(username, ip_address)
    cache.delete(key)


