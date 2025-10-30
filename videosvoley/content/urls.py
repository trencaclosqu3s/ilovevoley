"""
URLs para la app content.
Migradas desde videos.urls para la nueva app content.
"""
from django.urls import path
from . import views

app_name = 'content'

urlpatterns = [
    # Videos
    path('', views.video_list, name='video_list'),
    path('nuevo/', views.video_create, name='video_create'),
    path('<int:video_id>/', views.video_detail, name='video_detail'),
    
    # Imágenes
    path('imagenes/', views.image_gallery, name='image_gallery'),
    path('imagenes/individual/', views.image_gallery, name='image_gallery_individual'),
    path('imagenes/albums/', views.image_gallery_albums, name='image_gallery_albums'),
    path('imagenes/subir/', views.image_upload, name='image_upload'),
    path('imagenes/subir-masivo/', views.image_bulk_upload, name='image_bulk_upload'),
    path('imagenes/<int:image_id>/', views.image_detail, name='image_detail'),
    path('imagenes/partido/<int:match_id>/', views.match_images, name='match_images'),
    path('imagenes/album/<uuid:album_group_id>/', views.album_group_images, name='album_group_images'),
    
    # Moderación (solo staff)
    path('moderacion/', views.image_moderation, name='image_moderation'),
    path('moderacion/<int:image_id>/', views.image_moderate_action, name='image_moderate_action'),
    path('moderacion/masiva/', views.image_moderate_bulk, name='image_moderate_bulk'),
    
    # Panel de moderación (solo superusers)
    path('panel-moderacion/', views.moderation_panel, name='moderation_panel'),
    
    # APIs
    path('api/moderacion/contadores/', views.moderation_counts_api, name='moderation_counts_api'),
    path('api/usuarios/<int:user_id>/aprobar/', views.approve_user_api, name='approve_user_api'),
    path('api/usuarios/<int:user_id>/rechazar/', views.reject_user_api, name='reject_user_api'),
    path('api/imagenes/<int:image_id>/moderar/', views.moderate_image_api, name='moderate_image_api'),
    
    # Páginas estáticas
    path('acerca-de/', views.about, name='about'),
]