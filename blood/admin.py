from django.contrib import admin
from .models import Donation


@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'donor',
        'blood_group',
        'donation_date',
        'units',
        'status',
    )

    list_filter = ('status', 'blood_group', 'donation_date')
    search_fields = ('donor__username', 'donor__email')
    readonly_fields = ('status', 'created_at')
