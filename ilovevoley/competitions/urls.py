from django.urls import path
from . import views
from .calendar_feed import UserMatchesFeed
from .scoreboard_api import (
    api_live_scoreboard,
    api_scoreboard_live_state,
    api_scoreboard_match_mark,
    api_scoreboard_match_result,
    api_scoreboard_matches_today,
    api_scoreboard_stream_ended,
    api_scoreboard_stream_live,
)

app_name = 'competitions'

urlpatterns = [
    # URLs de ligas y partidos
    path('ligas/', views.league_list, name='league_list'),
    path('ligas/<int:league_id>/', views.league_detail, name='league_detail'),
    path('partidos/<int:match_id>/', views.match_detail, name='match_detail'),
    path('match/<int:match_id>/live-state/', api_live_scoreboard, name='match_live_state'),
    path('partidos/<int:match_id>/jugadas/<int:mark_id>/jugadores/', views.match_mark_persons, name='match_mark_persons'),
    path('partidos/<int:match_id>/jugadas/<int:mark_id>/clip/', views.match_mark_clip, name='match_mark_clip'),
    path('partidos/<int:match_id>/compartir/', views.match_share_create, name='match_share_create'),
    path('partidos/<int:match_id>/compartir/<int:link_id>/revocar/', views.match_share_revoke, name='match_share_revoke'),
    path('partidos/<int:match_id>/tarjeta/', views.match_result_card, name='match_result_card'),
    path('partidos/<int:match_id>/tarjeta/guardar/', views.story_composition_save, name='story_composition_save'),
    path('composiciones/<int:composition_id>/borrar/', views.story_composition_delete, name='story_composition_delete'),
    path('calendario/', views.calendar_view, name='calendar_view'),
    path('resultados/', views.results_view, name='results_view'),
    path('clasificacion/', views.standings_view, name='standings_view'),
    path('calendario/amistoso/nuevo/', views.friendly_match_create, name='friendly_match_create'),
    path('cambios-jornada/', views.match_changes_review, name='match_changes_review'),

    # Calendar subscription feed (ICS)
    path('calendario/suscripcion/<str:token>/', UserMatchesFeed(), name='calendar_feed'),

    # URLs AJAX
    path('ajax/matches-by-category/', views.ajax_matches_by_category, name='ajax_matches_by_category'),
    path('ajax/teams-by-league-category/', views.ajax_teams_by_league_category, name='ajax_teams_by_league_category'),
    path('ajax/results/teams/', views.ajax_results_teams, name='ajax_results_teams'),
    path('ajax/search-teams/', views.ajax_search_teams, name='ajax_search_teams'),
    path('ajax/partidos/<int:match_id>/resultado/', views.ajax_add_match_result, name='ajax_add_match_result'),
    path('ajax/partidos/<int:match_id>/parciales/', views.ajax_edit_match_result, name='ajax_edit_match_result'),
    path('ajax/partidos/<int:match_id>/alineacion/', views.ajax_acta_lineup, name='ajax_acta_lineup'),
    path('ajax/partidos/<int:match_id>/alineacion/vincular/', views.ajax_link_acta_person, name='ajax_link_acta_person'),
    path('ajax/partidos/<int:match_id>/stream/', views.ajax_update_stream_url, name='ajax_update_stream_url'),
    path('api/stream/live/', api_scoreboard_stream_live, name='api_scoreboard_stream_live'),
    path('api/stream/ended/', api_scoreboard_stream_ended, name='api_scoreboard_stream_ended'),
    path('api/matches/today/', api_scoreboard_matches_today, name='api_scoreboard_matches_today'),
    path('api/match/result/', api_scoreboard_match_result, name='api_scoreboard_match_result'),
    path('api/match/mark/', api_scoreboard_match_mark, name='api_scoreboard_match_mark'),
    path('api/match/live-state/', api_scoreboard_live_state, name='api_scoreboard_live_state'),
    path('ajax/cambios/<int:log_id>/marcar-revisado/', views.ajax_mark_change_reviewed, name='ajax_mark_change_reviewed'),

]
