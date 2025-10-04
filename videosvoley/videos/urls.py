from django.urls import path
from . import views

urlpatterns = [
    path('', views.video_list, name='video_list'),
    path('nuevo/', views.video_create, name='video_create'),
]