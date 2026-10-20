
from django.urls import path
from . import views

urlpatterns = [
    path('donations/submit/', views.submit_donation, name='submit_donation'),
]
