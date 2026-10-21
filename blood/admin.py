from django.contrib import admin
from .models import Donation, BloodInventory


@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'donor',
        'blood_group',
        'donation_date',
        'units',
        'status',
        'reviewed_by',
    )
    list_filter = ('status', 'blood_group', 'donation_date')
    search_fields = ('donor__username', 'donor__email')
    readonly_fields = ('status', 'created_at', 'reviewed_by', 'reviewed_at')


@admin.register(BloodInventory)
class BloodInventoryAdmin(admin.ModelAdmin):
    list_display = ('blood_group', 'units', 'updated_at')
    list_filter = ('blood_group',)
