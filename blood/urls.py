from django.urls import path
from . import views

urlpatterns = [
    path(
        'donations/submit/',
        views.submit_donation,
        name='submit_donation'
    ),
    path(
        'requests/submit/',
        views.submit_blood_request,
        name='submit_blood_request'
    ),
    path(
        'staff/donations/',
        views.manage_donations,
        name='manage_donations'
    ),
    path(
        'staff/donations/<int:donation_id>/review/',
        views.review_donation,
        name='review_donation'
    ),
    path(
        'inventory/availability/',
        views.view_blood_availability,
        name='blood_availability'
    ),
    path(
        'donations/history/',
        views.donation_history,
        name='donation_history'
    ),
    path(
        'requests/history/',
        views.blood_request_history,
        name='blood_request_history'
    ),
]
