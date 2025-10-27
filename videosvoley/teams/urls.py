"""
URLs para la app teams.
Migradas desde videos.urls para la nueva app teams.
"""
from django.urls import path
from . import views

app_name = 'teams'

urlpatterns = [
    # Equipos
    path('equipos/', views.team_list, name='team_list'),
    path('equipos/<int:team_id>/', views.team_detail, name='team_detail'),
    path('equipos/<int:team_id>/plantilla/', views.team_roster, name='team_roster'),
    
    # Clubs
    path('clubs/', views.club_list, name='club_list'),
    path('clubs/<int:club_id>/', views.club_detail, name='club_detail'),
    
    # Plantillas
    path('plantillas/', views.roster_overview, name='roster_overview'),
    
    # APIs AJAX
    path('api/equipos/buscar/', views.ajax_search_teams, name='ajax_search_teams'),
    path('api/equipos/por-liga-categoria/', views.ajax_teams_by_league_category, name='ajax_teams_by_league_category'),
    path('api/equipos/registrar/', views.ajax_register_team, name='ajax_register_team'),
    path('api/clubs/buscar/', views.ajax_search_clubs, name='ajax_search_clubs'),
]