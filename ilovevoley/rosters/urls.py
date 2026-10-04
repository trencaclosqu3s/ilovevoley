from django.urls import path
from . import views

app_name = 'rosters'

urlpatterns = [
    path('plantillas/', views.roster_overview, name='roster_overview'),
    path('personas/', views.person_list, name='person_list'),
    path('personas/nueva/', views.person_create, name='person_create'),
    path('personas/yo/', views.my_profile, name='my_profile'),
    path('personas/<int:person_id>/', views.person_detail, name='person_detail'),
    path('personas/<int:person_id>/editar/', views.person_edit, name='person_edit'),
    path('personas/<int:person_id>/jugador/agregar/', views.player_role_create, name='player_role_create'),
    path('roles-jugador/<int:role_id>/editar/', views.player_role_edit, name='player_role_edit'),
    path('roles-jugador/<int:role_id>/toggle/', views.player_role_toggle_active, name='player_role_toggle_active'),
    path('personas/<int:person_id>/staff/agregar/', views.staff_role_create, name='staff_role_create'),
    path('roles-staff/<int:role_id>/editar/', views.staff_role_edit, name='staff_role_edit'),
    path('roles-staff/<int:role_id>/toggle/', views.staff_role_toggle_active, name='staff_role_toggle_active'),
]
