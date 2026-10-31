from django.contrib.auth.models import User
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

