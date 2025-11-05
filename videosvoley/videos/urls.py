"""
URLs para la app videos.
Las URLs han sido migradas a las nuevas apps específicas.
Este archivo mantiene las referencias para compatibilidad hacia atrás.
"""

from django.urls import path
from .calendar_feed import UserMatchesFeed

app_name = 'videos'

# Import views from new apps for compatibility redirects
from videosvoley.content import views as content_views
from videosvoley.competitions import views as competitions_views
from videosvoley.teams import views as teams_views
from videosvoley.rosters import views as rosters_views

# URLs de compatibilidad específicas para evitar NoReverseMatch
urlpatterns = [
    # Páginas principales de content
    path('', content_views.video_list, name='video_list'),
    path('nuevo/', content_views.video_create, name='video_create'),
    path('<int:video_id>/', content_views.video_detail, name='video_detail'),
    
    # Imágenes
    path('imagenes/', content_views.image_gallery, name='image_gallery'),
    path('imagenes/individual/', content_views.image_gallery, name='image_gallery_individual'),
    path('imagenes/albums/', content_views.image_gallery_albums, name='image_gallery_albums'),
    path('imagenes/subir/', content_views.image_upload, name='image_upload'),
    path('imagenes/subir-masivo/', content_views.image_bulk_upload, name='image_bulk_upload'),
    path('imagenes/<int:image_id>/', content_views.image_detail, name='image_detail'),
    path('imagenes/partido/<int:match_id>/', content_views.match_images, name='match_images'),
    path('imagenes/album/<uuid:album_group_id>/', content_views.album_group_images, name='album_group_images'),
    
    # Moderación
    path('moderacion/', content_views.image_moderation, name='image_moderation'),
    path('moderacion/<int:image_id>/', content_views.image_moderate_action, name='image_moderate_action'),
    path('moderacion/masiva/', content_views.image_moderate_bulk, name='image_moderate_bulk'),
    path('panel-moderacion/', content_views.moderation_panel, name='moderation_panel'),
    
    # Páginas estáticas
    path('acerca-de/', content_views.about, name='about'),
    
    # APIs content
    path('api/moderacion/contadores/', content_views.moderation_counts_api, name='moderation_counts_api'),
    path('api/usuarios/<int:user_id>/aprobar/', content_views.approve_user_api, name='approve_user_api'),
    path('api/usuarios/<int:user_id>/rechazar/', content_views.reject_user_api, name='reject_user_api'),
    path('api/imagenes/<int:image_id>/moderar/', content_views.moderate_image_api, name='moderate_image_api'),
    
    # Competitions URLs
    path('ligas/', competitions_views.league_list, name='league_list'),
    path('ligas/<int:league_id>/', competitions_views.league_detail, name='league_detail'),
    path('partidos/<int:match_id>/', competitions_views.match_detail, name='match_detail'),
    path('partidos/amistoso/', competitions_views.friendly_match_create, name='friendly_match_create'),
    path('calendario/', competitions_views.calendar_view, name='calendar_view'),
    path('clasificaciones/', competitions_views.standings_view, name='standings_view'),
    
    # Teams URLs
    path('equipos/', teams_views.team_list, name='team_list'),
    path('equipos/<int:team_id>/', teams_views.team_detail, name='team_detail'),
    path('equipos/<int:team_id>/plantilla/', teams_views.team_roster, name='team_roster'),
    path('clubs/', teams_views.club_list, name='club_list'),
    path('clubs/<int:club_id>/', teams_views.club_detail, name='club_detail'),
    
    # Rosters URLs
    path('personas/', rosters_views.person_list, name='person_list'),
    path('personas/<int:person_id>/', rosters_views.person_detail, name='person_detail'),
    path('plantillas/', rosters_views.roster_overview, name='roster_overview'),
    
    # AJAX APIs
    path('ajax/equipos/buscar/', competitions_views.ajax_search_teams, name='ajax_search_teams'),
    path('ajax/partidos/<int:match_id>/resultado/', competitions_views.ajax_add_match_result, name='ajax_add_match_result'),
    path('ajax/partidos/por-categoria/', competitions_views.ajax_matches_by_category, name='ajax_matches_by_category'),
    path('ajax/equipos/por-liga-categoria/', competitions_views.ajax_teams_by_league_category, name='ajax_teams_by_league_category'),
    path('ajax/equipos/registrar/', competitions_views.ajax_register_team, name='ajax_register_team'),
    
    # MANTENER COMPATIBILIDAD HACIA ATRÁS - Calendar feed
    # Los usuarios que ya tienen el calendario suscrito no tendrán que volver a suscribirse
    path('calendario/suscripcion/<str:token>/', UserMatchesFeed(), name='calendar_feed'),
]