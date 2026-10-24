from django.urls import path

from . import views

app_name = 'public'

urlpatterns = [
    path('partido/<uuid:token>/', views.public_match_timeline, name='match_timeline'),
    path('partido/<uuid:token>/media/<int:image_id>/', views.public_match_media, name='match_media'),
    path('partido/<uuid:token>/jugadas/<int:mark_id>/clip/', views.public_match_mark_clip, name='match_mark_clip'),
]
