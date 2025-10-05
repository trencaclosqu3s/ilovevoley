from django.urls import path
from . import views

urlpatterns = [
    path('', views.video_list, name='video_list'),
    path('nuevo/', views.video_create, name='video_create'),
    path('<int:video_id>/', views.video_detail, name='video_detail'),
    path('ligas/', views.league_list, name='league_list'),
    path('ligas/<int:league_id>/', views.league_detail, name='league_detail'),
    path('partidos/<int:match_id>/', views.match_detail, name='match_detail'),
    path('calendario/', views.calendar_view, name='calendar_view'),
    path('clasificacion/', views.standings_view, name='standings_view'),
    path('ajax/matches-by-category/', views.ajax_matches_by_category, name='ajax_matches_by_category'),
    path('ajax/teams-by-league-category/', views.ajax_teams_by_league_category, name='ajax_teams_by_league_category'),
]