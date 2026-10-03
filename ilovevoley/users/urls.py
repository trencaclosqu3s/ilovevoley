from django.urls import path
from . import views

urlpatterns = [
    path('pending-approval/', views.pending_approval, name='pending_approval'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),
    path('get-calendar-token/', views.get_calendar_token, name='get_calendar_token'),
    path('regenerate-calendar-token/', views.regenerate_calendar_token, name='regenerate_calendar_token'),
    # Endpoints Web Push PWA
    path('api/webpush/vapid-key/', views.webpush_vapid_key, name='webpush_vapid_key'),
    path('api/webpush/subscribe/', views.webpush_subscribe, name='webpush_subscribe'),
    path('api/webpush/unsubscribe/', views.webpush_unsubscribe, name='webpush_unsubscribe'),
    path('deactivate-account/<str:token>/', views.deactivate_account_view, name='deactivate_account'),
]