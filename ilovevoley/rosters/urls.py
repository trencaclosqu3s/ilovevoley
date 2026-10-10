from django.urls import path
from . import views

app_name = 'rosters'

urlpatterns = [
    path('plantillas/', views.roster_overview, name='roster_overview'),
    path('personas/', views.person_list, name='person_list'),
    path('personas/nueva/', views.person_create, name='person_create'),
    path('personas/crear-rapido/', views.person_quick_create, name='person_quick_create'),
    path('personas/adoptar/', views.person_adopt, name='person_adopt'),
    path('personas/yo/', views.my_profile, name='my_profile'),
    path('personas/yo/hijos/<int:person_id>/', views.child_profile, name='child_profile'),
    path('personas/<int:person_id>/', views.person_detail, name='person_detail'),
    path('personas/<int:person_id>/baja-alta/', views.person_membership_toggle, name='person_membership_toggle'),
    path('personas/<int:person_id>/cromo/', views.person_card_page, name='person_card_page'),
    path('personas/<int:person_id>/cromo.png', views.person_card, name='person_card'),
    path('personas/<int:person_id>/wrapped/', views.season_wrapped_page, name='season_wrapped_page'),
    path('personas/<int:person_id>/wrapped/<int:n>.png', views.season_wrapped_png, name='season_wrapped_png'),
    path('personas/<int:person_id>/editar/', views.person_edit, name='person_edit'),
    path('personas/<int:person_id>/jugador/agregar/', views.player_role_create, name='player_role_create'),
    path('plantillas/<int:team_id>/jugadores/agregar/', views.player_roster_bulk_add, name='player_roster_bulk_add'),
    path('roles-jugador/<int:role_id>/editar/', views.player_role_edit, name='player_role_edit'),
    path('roles-jugador/<int:role_id>/toggle/', views.player_role_toggle_active, name='player_role_toggle_active'),
    path('personas/<int:person_id>/staff/agregar/', views.staff_role_create, name='staff_role_create'),
    path('roles-staff/<int:role_id>/editar/', views.staff_role_edit, name='staff_role_edit'),
    path('roles-staff/<int:role_id>/toggle/', views.staff_role_toggle_active, name='staff_role_toggle_active'),
]
