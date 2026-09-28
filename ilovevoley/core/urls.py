"""
URLs for core app - error handling, pages, and user moderation.
"""
from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Error page testing (development only)
    path('test/400/', views.test_400, name='test_400'),
    path('test/403/', views.test_403, name='test_403'), 
    path('test/404/', views.test_404, name='test_404'),
    path('test/500/', views.test_500, name='test_500'),
    
    # Páginas institucionales
    path('quienes-somos/', views.about, name='about'),
    
    # Moderación de usuarios
    path('moderacion/', views.moderation_panel, name='moderation_panel'),
    path('api/moderation/counts/', views.moderation_counts_api, name='moderation_counts_api'),
    path('api/users/<int:user_id>/approve/', views.approve_user_api, name='approve_user_api'),
    path('api/users/<int:user_id>/reject/', views.reject_user_api, name='reject_user_api'),

    # Wizard de nueva temporada (plataforma, solo superusers)
    path('temporadas/nueva/', views.season_wizard, name='season_wizard'),
    path('temporadas/nueva/confirmar/', views.season_wizard_confirm, name='season_wizard_confirm'),
]