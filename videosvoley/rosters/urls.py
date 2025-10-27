from django.urls import path
from . import views

app_name = 'rosters'

urlpatterns = [
    # URLs de personas
    path('personas/', views.person_list, name='person_list'),
    path('personas/<int:person_id>/', views.person_detail, name='person_detail'),
    path('personas/<int:person_id>/estadisticas/', views.person_statistics, name='person_statistics'),
    
    # URLs de plantillas de equipos
    path('equipos/<int:team_id>/plantilla/', views.team_roster, name='team_roster'),
    path('equipos/<int:team_id>/plantilla/posiciones/', views.roster_by_position, name='roster_by_position'),
    path('equipos/<int:team_id>/plantilla/exportar/', views.roster_export, name='roster_export'),
    
    # URLs de búsqueda (AJAX)
    path('buscar/personas/', views.search_persons, name='search_persons'),
    
    # URLs de gestión (AJAX)
    path('asignar-dorsal/<int:role_id>/', views.assign_jersey_number, name='assign_jersey_number'),
]