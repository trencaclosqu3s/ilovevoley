from django.urls import path

from . import portal_views

app_name = 'portal'

urlpatterns = [
    path('', portal_views.index, name='index'),
    path('ligas/', portal_views.league_list, name='league_list'),
]
