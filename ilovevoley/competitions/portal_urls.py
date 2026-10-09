from django.urls import path

from . import portal_views

app_name = 'portal'

urlpatterns = [
    path('', portal_views.index, name='index'),
    path('ligas/', portal_views.league_list, name='league_list'),
    path('ligas/<int:league_id>/', portal_views.league_detail, name='league_detail'),
    path('calendario/', portal_views.calendar_view, name='calendar'),
    path('resultados/', portal_views.results_view, name='results'),
    path('clasificacion/', portal_views.standings_view, name='standings'),
]
