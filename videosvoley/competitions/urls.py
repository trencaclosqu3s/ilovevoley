from django.urls import path
from . import views

app_name = 'competitions'

urlpatterns = [
    # URLs de ligas
    path('ligas/', views.league_list, name='league_list'),
    path('ligas/<int:league_id>/', views.league_detail, name='league_detail'),
    path('ligas/<int:league_id>/clasificacion/', views.standings, name='standings'),
    
    # URLs de partidos
    path('partidos/', views.match_calendar, name='match_calendar'),
    path('partidos/<int:match_id>/', views.match_detail, name='match_detail'),
    path('partidos/amistoso/nuevo/', views.friendly_match_create, name='friendly_match_create'),
]