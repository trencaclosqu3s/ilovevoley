from django.urls import path
from . import views

app_name = 'teams'

urlpatterns = [
    path('equipos/', views.team_list, name='team_list'),
    path('equipos/<int:team_id>/plantilla/', views.team_roster, name='team_roster'),
    path('ajax/register-team/', views.ajax_register_team, name='ajax_register_team'),
]
