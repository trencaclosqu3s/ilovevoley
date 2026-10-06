from django.urls import path
from . import views
from . import views_album_zip

app_name = 'content'

urlpatterns = [
    # URLs de videos
    path('', views.video_list, name='video_list'),
    path('nuevo/', views.video_create, name='video_create'),
    path('nuevo-multiple/', views.video_bulk_create, name='video_bulk_create'),
    path('<int:video_id>/', views.video_detail, name='video_detail'),
    
    # URLs de imágenes
    path('imagenes/', views.image_gallery_albums, name='image_gallery'),
    path('imagenes/individual/', views.image_gallery, name='image_gallery_individual'),
    path('imagenes/subir/', views.image_upload, name='image_upload'),
    path('imagenes/subir-multiples/', views.image_bulk_upload, name='image_bulk_upload'),
    path('imagenes/<int:image_id>/', views.image_detail, name='image_detail'),
    path('imagenes/<int:image_id>/etiquetar/', views.image_tag, name='image_tag'),
    path('imagenes/etiquetar/', views.image_tag_bulk, name='image_tag_bulk'),
    path('partidos/<int:match_id>/imagenes/', views.match_images, name='match_images'),
    path(
        'partidos/<int:match_id>/imagenes/zip/',
        views_album_zip.request_match_album_zip,
        name='match_album_zip',
    ),
    path('imagenes/album/<uuid:album_group_id>/', views.album_group_images, name='album_group_images'),
    path(
        'imagenes/album/<uuid:album_group_id>/zip/',
        views_album_zip.request_album_group_zip,
        name='album_group_zip',
    ),
    path(
        'imagenes/zip/<uuid:job_id>/',
        views_album_zip.album_zip_status,
        name='album_zip_status',
    ),
    path(
        'imagenes/zip/download/',
        views_album_zip.album_zip_download,
        name='album_zip_download',
    ),
    
    # URLs de moderación de imágenes
    path('admin/imagenes/moderar/', views.image_moderation, name='image_moderation'),
    path('admin/imagenes/<int:image_id>/moderar/', views.image_moderate_action, name='image_moderate_action'),
    path('admin/imagenes/moderar-masivo/', views.image_moderate_bulk, name='image_moderate_bulk'),
    path('api/images/<int:image_id>/moderate/', views.moderate_image_api, name='moderate_image_api'),
]
