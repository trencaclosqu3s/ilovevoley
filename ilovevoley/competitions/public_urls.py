from django.urls import path

from . import views

app_name = 'public'

urlpatterns = [
    path('partido/<uuid:token>/', views.public_match_timeline, name='match_timeline'),
    path('partido/<uuid:token>/media/<int:image_id>/', views.public_match_media, name='match_media'),
]
