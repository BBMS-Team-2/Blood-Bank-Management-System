from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import Donation, BloodInventory, BloodRequest


@transaction.atomic
def review_donation(donation_id, reviewer, action):
    if action not in ('approve', 'reject'):
        raise ValueError("Action must be 'approve' or 'reject'.")

    try:
        donation = Donation.objects.get(pk=donation_id)
    except Donation.DoesNotExist:
        return False

    new_status = 'Approved' if action == 'approve' else 'Rejected'

    # Claim the pending donation exactly once.
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
        inventory, _ = BloodInventory.objects.get_or_create(
            blood_group=donation.blood_group,
            defaults={
                'units': 0,
                'expiry_date': donation.expiry_date,
            }
        )

        update_kwargs = {'units': F('units') + donation.units}
        if donation.expiry_date and (not inventory.expiry_date or donation.expiry_date < inventory.expiry_date):
            update_kwargs['expiry_date'] = donation.expiry_date

        BloodInventory.objects.filter(pk=inventory.pk).update(**update_kwargs)

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

    BloodInventory.objects.filter(pk=inventory.pk).update(
        units=F('units') - blood_request.units
    )

    return True
