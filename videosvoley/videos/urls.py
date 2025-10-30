from django.urls import path
from . import views
from .calendar_feed import UserMatchesFeed

app_name = 'videos'

urlpatterns = [
    # URLs de videos
    path('', views.video_list, name='video_list'),
    path('nuevo/', views.video_create, name='video_create'),
    path('<int:video_id>/', views.video_detail, name='video_detail'),
    
    # URLs de ligas y partidos
    path('ligas/', views.league_list, name='league_list'),
    path('ligas/<int:league_id>/', views.league_detail, name='league_detail'),
    path('partidos/<int:match_id>/', views.match_detail, name='match_detail'),
    path('calendario/', views.calendar_view, name='calendar_view'),
    path('clasificacion/', views.standings_view, name='standings_view'),
    path('calendario/amistoso/nuevo/', views.friendly_match_create, name='friendly_match_create'),
    
    # URLs de plantillas
    path('equipos/', views.team_list, name='team_list'),
    path('equipos/<int:team_id>/plantilla/', views.team_roster, name='team_roster'),
    path('plantillas/', views.roster_overview, name='roster_overview'),
    
    # URLs de imágenes
    path('imagenes/', views.image_gallery_albums, name='image_gallery'),
    path('imagenes/individual/', views.image_gallery, name='image_gallery_individual'),
    path('imagenes/subir/', views.image_upload, name='image_upload'),
    path('imagenes/subir-multiples/', views.image_bulk_upload, name='image_bulk_upload'),
    path('imagenes/<int:image_id>/', views.image_detail, name='image_detail'),
    path('partidos/<int:match_id>/imagenes/', views.match_images, name='match_images'),
    path('imagenes/album/<uuid:album_group_id>/', views.album_group_images, name='album_group_images'),
    
    # URLs de moderación (solo admin)
    path('admin/imagenes/moderar/', views.image_moderation, name='image_moderation'),
    path('admin/imagenes/<int:image_id>/moderar/', views.image_moderate_action, name='image_moderate_action'),
    path('admin/imagenes/moderar-masivo/', views.image_moderate_bulk, name='image_moderate_bulk'),
    
    # URLs AJAX
    path('ajax/matches-by-category/', views.ajax_matches_by_category, name='ajax_matches_by_category'),
    path('ajax/teams-by-league-category/', views.ajax_teams_by_league_category, name='ajax_teams_by_league_category'),
    path('ajax/search-teams/', views.ajax_search_teams, name='ajax_search_teams'),
    path('ajax/register-team/', views.ajax_register_team, name='ajax_register_team'),
    path('ajax/partidos/<int:match_id>/resultado/', views.ajax_add_match_result, name='ajax_add_match_result'),
    
    # URLs de moderación y notificaciones (solo superuser)
    path('moderacion/', views.moderation_panel, name='moderation_panel'),
    path('api/moderation/counts/', views.moderation_counts_api, name='moderation_counts_api'),
    path('api/users/<int:user_id>/approve/', views.approve_user_api, name='approve_user_api'),
    path('api/users/<int:user_id>/reject/', views.reject_user_api, name='reject_user_api'),
    path('api/images/<int:image_id>/moderate/', views.moderate_image_api, name='moderate_image_api'),
    
    # Página institucional
    path('quienes-somos/', views.about, name='about'),
    
    # Calendar subscription feed (ICS)
    path('calendario/suscripcion/<str:token>/', UserMatchesFeed(), name='calendar_feed'),
    
    # URLs de gestión de personas
    path('personas/', views.person_list, name='person_list'),
    path('personas/nueva/', views.person_create, name='person_create'),
    path('personas/<int:person_id>/', views.person_detail, name='person_detail'),
    path('personas/<int:person_id>/editar/', views.person_edit, name='person_edit'),
    
    # URLs de roles de jugador
    path('personas/<int:person_id>/jugador/agregar/', views.player_role_create, name='player_role_create'),
    path('roles-jugador/<int:role_id>/editar/', views.player_role_edit, name='player_role_edit'),
    path('roles-jugador/<int:role_id>/toggle/', views.player_role_toggle_active, name='player_role_toggle_active'),
    
    # URLs de roles de staff
    path('personas/<int:person_id>/staff/agregar/', views.staff_role_create, name='staff_role_create'),
    path('roles-staff/<int:role_id>/editar/', views.staff_role_edit, name='staff_role_edit'),
    path('roles-staff/<int:role_id>/toggle/', views.staff_role_toggle_active, name='staff_role_toggle_active'),
]