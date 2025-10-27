"""
URLs para la app rosters.
Migradas desde videos.urls para la nueva app rosters.
"""
from django.urls import path
from . import views

app_name = 'rosters'

urlpatterns = [
    # Personas
    path('personas/', views.person_list, name='person_list'),
    path('personas/<int:person_id>/', views.person_detail, name='person_detail'),
    path('personas/crear/', views.person_create, name='person_create'),
    path('personas/<int:person_id>/editar/', views.person_edit, name='person_edit'),
    
    # Roles de jugador
    path('personas/<int:person_id>/jugador/', views.player_role_create, name='player_role_create'),
    path('roles/jugador/<int:role_id>/editar/', views.player_role_edit, name='player_role_edit'),
    path('roles/jugador/<int:role_id>/toggle/', views.player_role_toggle_active, name='player_role_toggle_active'),
    
    # Roles de staff
    path('personas/<int:person_id>/staff/', views.staff_role_create, name='staff_role_create'),
    path('roles/staff/<int:role_id>/editar/', views.staff_role_edit, name='staff_role_edit'),
    path('roles/staff/<int:role_id>/toggle/', views.staff_role_toggle_active, name='staff_role_toggle_active'),
    
    # Plantillas
    path('plantillas/', views.roster_overview, name='roster_overview'),
    
    # APIs AJAX
    path('api/personas/buscar/', views.ajax_search_persons, name='ajax_search_persons'),
    path('api/personas/por-equipo/', views.ajax_persons_by_team, name='ajax_persons_by_team'),
    path('api/personas/crear/', views.ajax_create_person, name='ajax_create_person'),
]