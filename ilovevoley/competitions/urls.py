from django.urls import path
from . import views
from .calendar_feed import UserMatchesFeed

app_name = 'competitions'

urlpatterns = [
    # URLs de ligas y partidos
    path('ligas/', views.league_list, name='league_list'),
    path('ligas/<int:league_id>/', views.league_detail, name='league_detail'),
    path('partidos/<int:match_id>/', views.match_detail, name='match_detail'),
    path('partidos/<int:match_id>/compartir/', views.match_share_create, name='match_share_create'),
    path('partidos/<int:match_id>/compartir/<int:link_id>/revocar/', views.match_share_revoke, name='match_share_revoke'),
    path('partidos/<int:match_id>/tarjeta/', views.match_result_card, name='match_result_card'),
    path('calendario/', views.calendar_view, name='calendar_view'),
    path('clasificacion/', views.standings_view, name='standings_view'),
    path('calendario/amistoso/nuevo/', views.friendly_match_create, name='friendly_match_create'),
    path('cambios-jornada/', views.match_changes_review, name='match_changes_review'),

    # Calendar subscription feed (ICS)
    path('calendario/suscripcion/<str:token>/', UserMatchesFeed(), name='calendar_feed'),

    # URLs AJAX
    path('ajax/matches-by-category/', views.ajax_matches_by_category, name='ajax_matches_by_category'),
    path('ajax/teams-by-league-category/', views.ajax_teams_by_league_category, name='ajax_teams_by_league_category'),
    path('ajax/search-teams/', views.ajax_search_teams, name='ajax_search_teams'),
    path('ajax/partidos/<int:match_id>/resultado/', views.ajax_add_match_result, name='ajax_add_match_result'),
    path('ajax/partidos/<int:match_id>/alineacion/', views.ajax_acta_lineup, name='ajax_acta_lineup'),
    path('ajax/cambios/<int:log_id>/marcar-revisado/', views.ajax_mark_change_reviewed, name='ajax_mark_change_reviewed'),

]
