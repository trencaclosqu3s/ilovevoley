"""
URL configuration for ilovevoley project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from ilovevoley.core.moderation_views import moderate_user, moderate_image
from ilovevoley.core.protected_media import protected_media
from ilovevoley.core.views import landing, healthz

urlpatterns = [
    re_path(r'^healthz/?$', healthz, name='healthz'),
    path(settings.ADMIN_URL, admin.site.urls),
    path('accounts/', include('allauth.urls')),
    # Alias para /videos/ preservando bookmarks hacia content:video_list y rutas legacy
    path('videos/', include('ilovevoley.videos.urls', namespace='videos')),
    path('rosters/', include('ilovevoley.rosters.urls', namespace='rosters')),
    path('content/', include('ilovevoley.content.urls', namespace='content')),
    path('teams/', include('ilovevoley.teams.urls', namespace='teams')),
    path('competitions/', include('ilovevoley.competitions.urls', namespace='competitions')),
    path('core/', include('ilovevoley.core.urls', namespace='core')),
    path('', include('ilovevoley.users.urls')),
    # Rutas de moderación con tokens seguros
    path('moderate/user/<str:token>/', moderate_user, name='moderate_user'),
    path('moderate/image/<str:token>/', moderate_image, name='moderate_image'),
    # Medios privados servidos vía X-Accel-Redirect (nginx) o FileResponse en dev
    path('media/<path:path>', protected_media, name='protected_media'),
    # Landing page and tenant redirect
    path('', landing, name='landing'),
]

if settings.DEBUG:
    # Test URLs para ver las páginas de error
    from ilovevoley.core.views import test_400, test_403, test_404, test_500
    urlpatterns += [
        path('test-error/400/', test_400, name='test_400'),
        path('test-error/403/', test_403, name='test_403'),
        path('test-error/404/', test_404, name='test_404'),
        path('test-error/500/', test_500, name='test_500'),
    ]

# Custom error handlers
handler400 = 'ilovevoley.core.views.custom_400'
handler403 = 'ilovevoley.core.views.custom_403'
handler404 = 'ilovevoley.core.views.custom_404'
handler500 = 'ilovevoley.core.views.custom_500'
