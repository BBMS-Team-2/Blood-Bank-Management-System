from django.contrib import admin, messages

from .models import Donation, BloodInventory, BloodRequest, PatientProfile
from .services import review_donation


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
    readonly_fields = (
        'status',
        'created_at',
        'reviewed_by',
        'reviewed_at',
    )

    actions = ('approve_donations', 'reject_donations')

    @admin.action(description='Approve selected pending donations')
    def approve_donations(self, request, queryset):
        self._review_selected(request, queryset, 'approve')

    @admin.action(description='Reject selected pending donations')
    def reject_donations(self, request, queryset):
        self._review_selected(request, queryset, 'reject')

    def _review_selected(self, request, queryset, action):
        completed = 0

        for donation_id in queryset.values_list('id', flat=True):
            if review_donation(donation_id, request.user, action):
                completed += 1

        self.message_user(
            request,
            f'{completed} donation(s) {action}d. '
            f'Already reviewed or missing: {queryset.count() - completed}.',
            level=messages.SUCCESS if completed else messages.WARNING,
        )


@admin.register(BloodInventory)
class BloodInventoryAdmin(admin.ModelAdmin):
    list_display = ('blood_group', 'units', 'updated_at')
    list_filter = ('blood_group',)


@admin.register(BloodRequest)
class BloodRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'patient', 'blood_group', 'units', 'needed_by_date', 'status', 'created_at')
    list_filter = ('status', 'blood_group')
    search_fields = ('patient__username',)


@admin.register(PatientProfile)
class PatientProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'blood_group', 'age', 'contact_phone', 'updated_at')
    search_fields = ('user__username', 'contact_phone')
