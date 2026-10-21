from django.urls import path
from . import views

urlpatterns = [
    path(
        'donations/submit/',
        views.submit_donation,
        name='submit_donation'
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
]
