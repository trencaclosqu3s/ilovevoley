"""
URLs para la app competitions.
Migradas desde videos.urls para la nueva app competitions.
"""
from django.urls import path
from . import views
from .calendar_feed import UserMatchesFeed

app_name = 'competitions'

urlpatterns = [
    # Ligas
    path('ligas/', views.league_list, name='league_list'),
    path('ligas/<int:league_id>/', views.league_detail, name='league_detail'),
    
    # Partidos (NOTA: Estas URLs se exponen bajo /videos/partidos/ desde videos.urls)
    path('<int:match_id>/', views.match_detail, name='match_detail'),  # Detalle de partido
    path('amistoso/', views.friendly_match_create, name='friendly_match_create'),
    
    # Calendario y clasificaciones
    path('calendario/', views.calendar_view, name='calendar_view'),
    path('clasificaciones/', views.standings_view, name='standings_view'),
    
    # APIs AJAX
    path('api/equipos/buscar/', views.ajax_search_teams, name='ajax_search_teams'),
    path('api/partidos/<int:match_id>/resultado/', views.ajax_add_match_result, name='ajax_add_match_result'),
    path('api/partidos/por-categoria/', views.ajax_matches_by_category, name='ajax_matches_by_category'),
    path('api/equipos/por-liga-categoria/', views.ajax_teams_by_league_category, name='ajax_teams_by_league_category'),
    path('api/equipos/registrar/', views.ajax_register_team, name='ajax_register_team'),
    
    # Calendar subscription feed (ICS)
    path('calendario/suscripcion/<str:token>/', UserMatchesFeed(), name='calendar_feed'),
]