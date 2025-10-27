from django.urls import path
from . import views

app_name = 'content'

urlpatterns = [
    # URLs de videos
    path('videos/', views.video_list, name='video_list'),
    path('videos/<int:video_id>/', views.video_detail, name='video_detail'),
    
    # URLs de imágenes
    path('imagenes/', views.image_gallery, name='image_gallery'),
    path('imagenes/<int:image_id>/', views.image_detail, name='image_detail'),
    path('imagenes/subir/', views.image_upload, name='image_upload'),
]