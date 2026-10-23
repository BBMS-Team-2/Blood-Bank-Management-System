from django.contrib import admin
from .models import Donation, BloodInventory, BloodRequest, PatientProfile


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


@admin.register(BloodRequest)
class BloodRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'patient', 'blood_group', 'units', 'needed_by_date', 'status', 'created_at')
    list_filter = ('status', 'blood_group')
    search_fields = ('patient__username',)


@admin.register(PatientProfile)
class PatientProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'blood_group', 'age', 'contact_phone', 'updated_at')
    search_fields = ('user__username', 'contact_phone')

