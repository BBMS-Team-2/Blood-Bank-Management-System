from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import Donation, BloodInventory


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
            defaults={'units': 0}
        )

        BloodInventory.objects.filter(pk=inventory.pk).update(
            units=F('units') + donation.units
        )

    return True
