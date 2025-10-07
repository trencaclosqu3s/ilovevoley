from django.urls import path
from . import views

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
    
    # URLs de imágenes
    path('imagenes/', views.image_gallery, name='image_gallery'),
    path('imagenes/subir/', views.image_upload, name='image_upload'),
    path('imagenes/<int:image_id>/', views.image_detail, name='image_detail'),
    path('partidos/<int:match_id>/imagenes/', views.match_images, name='match_images'),
    
    # URLs de moderación (solo admin)
    path('admin/imagenes/moderar/', views.image_moderation, name='image_moderation'),
    path('admin/imagenes/<int:image_id>/moderar/', views.image_moderate_action, name='image_moderate_action'),
    path('admin/imagenes/moderar-masivo/', views.image_moderate_bulk, name='image_moderate_bulk'),
    
    # URLs AJAX
    path('ajax/matches-by-category/', views.ajax_matches_by_category, name='ajax_matches_by_category'),
    path('ajax/teams-by-league-category/', views.ajax_teams_by_league_category, name='ajax_teams_by_league_category'),
    
    # Página institucional
    path('quienes-somos/', views.about, name='about'),
]