from django.urls import path
from . import views

urlpatterns = [
    path('pending-approval/', views.pending_approval, name='pending_approval'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),
    path('get-calendar-token/', views.get_calendar_token, name='get_calendar_token'),
    path('regenerate-calendar-token/', views.regenerate_calendar_token, name='regenerate_calendar_token'),
]