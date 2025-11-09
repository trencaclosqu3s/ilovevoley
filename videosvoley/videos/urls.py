"""
URLs de compatibilidad para la app videos.
Mantiene redirects HTTP para compatibilidad hacia atrás con URLs externas.
Las nuevas URLs están en las apps refactorizadas: content, competitions, teams, rosters.
"""

from django.urls import path
from django.views.generic import RedirectView
from .calendar_feed import UserMatchesFeed

app_name = 'videos'

# URLs de compatibilidad - redirects HTTP permanentes a las nuevas apps
urlpatterns = [
    # Content redirects
    path('', RedirectView.as_view(url='/', permanent=True), name='video_list'),
    path('nuevo/', RedirectView.as_view(url='/nuevo/', permanent=True), name='video_create'),
    path('<int:video_id>/', RedirectView.as_view(url='/%(video_id)s/', permanent=True), name='video_detail'),
    
    # Imágenes redirects
    path('imagenes/', RedirectView.as_view(url='/imagenes/', permanent=True), name='image_gallery'),
    path('imagenes/individual/', RedirectView.as_view(url='/imagenes/', permanent=True), name='image_gallery_individual'),
    path('imagenes/albums/', RedirectView.as_view(url='/imagenes/albums/', permanent=True), name='image_gallery_albums'),
    path('imagenes/subir/', RedirectView.as_view(url='/imagenes/subir/', permanent=True), name='image_upload'),
    path('imagenes/subir-masivo/', RedirectView.as_view(url='/imagenes/subir-masivo/', permanent=True), name='image_bulk_upload'),
    path('imagenes/<int:image_id>/', RedirectView.as_view(url='/imagenes/%(image_id)s/', permanent=True), name='image_detail'),
    path('imagenes/partido/<int:match_id>/', RedirectView.as_view(url='/imagenes/partido/%(match_id)s/', permanent=True), name='match_images'),
    path('imagenes/album/<uuid:album_group_id>/', RedirectView.as_view(url='/imagenes/album/%(album_group_id)s/', permanent=True), name='album_group_images'),
    
    # Moderación redirects
    path('moderacion/', RedirectView.as_view(url='/moderacion/', permanent=True), name='image_moderation'),
    path('moderacion/<int:image_id>/', RedirectView.as_view(url='/moderacion/%(image_id)s/', permanent=True), name='image_moderate_action'),
    path('moderacion/masiva/', RedirectView.as_view(url='/moderacion/masiva/', permanent=True), name='image_moderate_bulk'),
    path('panel-moderacion/', RedirectView.as_view(url='/panel-moderacion/', permanent=True), name='moderation_panel'),
    
    # Páginas estáticas redirects
    path('acerca-de/', RedirectView.as_view(url='/acerca-de/', permanent=True), name='about'),
    
    # Competitions redirects
    path('ligas/', RedirectView.as_view(url='/competiciones/', permanent=True), name='league_list'),
    path('ligas/<int:league_id>/', RedirectView.as_view(url='/competiciones/ligas/%(league_id)s/', permanent=True), name='league_detail'),
    path('partidos/<int:match_id>/', RedirectView.as_view(url='/competiciones/partidos/%(match_id)s/', permanent=True), name='match_detail'),
    path('partidos/amistoso/', RedirectView.as_view(url='/competiciones/partidos/amistoso/', permanent=True), name='friendly_match_create'),
    path('calendario/', RedirectView.as_view(url='/competiciones/calendario/', permanent=True), name='calendar_view'),
    path('clasificaciones/', RedirectView.as_view(url='/competiciones/clasificaciones/', permanent=True), name='standings_view'),
    
    # Teams redirects
    path('equipos/', RedirectView.as_view(url='/equipos/', permanent=True), name='team_list'),
    path('equipos/<int:team_id>/plantilla/', RedirectView.as_view(url='/equipos/%(team_id)s/plantilla/', permanent=True), name='team_roster'),
    
    # Rosters redirects
    path('personas/', RedirectView.as_view(url='/plantilla/personas/', permanent=True), name='person_list'),
    path('personas/<int:person_id>/', RedirectView.as_view(url='/plantilla/personas/%(person_id)s/', permanent=True), name='person_detail'),
    path('plantillas/', RedirectView.as_view(url='/plantilla/', permanent=True), name='roster_overview'),
    
    # MANTENER COMPATIBILIDAD HACIA ATRÁS - Calendar feed
    # Los usuarios que ya tienen el calendario suscrito no tendrán que volver a suscribirse
    path('calendario/suscripcion/<str:token>/', UserMatchesFeed(), name='calendar_feed'),
]