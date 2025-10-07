from django.urls import path
from . import views

urlpatterns = [
    path('pending-approval/', views.pending_approval, name='pending_approval'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),
]