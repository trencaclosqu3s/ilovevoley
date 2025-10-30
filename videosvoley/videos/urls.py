"""
URLs para la app videos.
Las URLs han sido migradas a las nuevas apps específicas.
Este archivo mantiene las referencias para compatibilidad hacia atrás.
"""

from django.urls import path, include
from .calendar_feed import UserMatchesFeed

app_name = 'videos'

# Incluir URLs de las nuevas apps para compatibilidad
urlpatterns = [
    # Redirigir a las nuevas apps
    path('', include('videosvoley.content.urls')),
    path('ligas/', include('videosvoley.competitions.urls')),
    path('partidos/', include('videosvoley.competitions.urls')),
    path('calendario/', include('videosvoley.competitions.urls')),
    path('clasificacion/', include('videosvoley.competitions.urls')),
    path('equipos/', include('videosvoley.teams.urls')),
    path('clubs/', include('videosvoley.teams.urls')),
    path('plantillas/', include('videosvoley.teams.urls')),
    path('imagenes/', include('videosvoley.content.urls')),
    path('personas/', include('videosvoley.rosters.urls')),
    path('roles/', include('videosvoley.rosters.urls')),
    path('moderacion/', include('videosvoley.content.urls')),
    path('quienes-somos/', include('videosvoley.content.urls')),
    
    # APIs AJAX (mantener para compatibilidad)
    path('ajax/', include('videosvoley.competitions.urls')),
    
    # MANTENER COMPATIBILIDAD HACIA ATRÁS - Calendar feed
    # Los usuarios que ya tienen el calendario suscrito no tendrán que volver a suscribirse
    path('calendario/suscripcion/<str:token>/', UserMatchesFeed(), name='calendar_feed'),
]