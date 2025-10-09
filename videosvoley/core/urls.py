"""
URLs for core app - Calendar and error handling.
"""
from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Calendar management
    path('calendar/settings/', views.calendar_settings, name='calendar_settings'),
    path('calendar/request-permissions/', views.request_calendar_permissions, name='request_calendar_permissions'),
    
    # Error page testing (development only)
    path('test/400/', views.test_400, name='test_400'),
    path('test/403/', views.test_403, name='test_403'), 
    path('test/404/', views.test_404, name='test_404'),
    path('test/500/', views.test_500, name='test_500'),
]