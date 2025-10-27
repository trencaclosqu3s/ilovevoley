from django.urls import path
from . import views

app_name = 'teams'

urlpatterns = [
    # URLs de clubs
    path('clubs/', views.club_list, name='club_list'),
    path('clubs/<int:club_id>/', views.club_detail, name='club_detail'),
    
    # URLs de equipos
    path('equipos/', views.team_list, name='team_list'),
    path('equipos/<int:team_id>/', views.team_detail, name='team_detail'),
    path('equipos/<int:team_id>/plantilla/', views.team_roster, name='team_roster'),
    path('equipos/<int:team_id>/estadisticas/', views.team_statistics, name='team_statistics'),
    
    # URLs de búsqueda (AJAX)
    path('buscar/equipos/', views.search_teams, name='search_teams'),
    path('buscar/clubs/', views.search_clubs, name='search_clubs'),
]