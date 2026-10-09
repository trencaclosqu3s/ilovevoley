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
from ilovevoley.competitions.views import where_plays, where_plays_search
from ilovevoley.core.moderation_views import moderate_user, moderate_image
from ilovevoley.core.protected_media import protected_media
from ilovevoley.core.views import (
    favicon,
    healthz,
    landing,
    manifest_json,
    offline_view,
    robots_txt,
    security_txt,
    service_worker,
    sitemap_xml,
    web_app_origin_association,
)
from ilovevoley.users.views import (
    RatelimitedLoginView,
    RatelimitedPasswordResetFromKeyView,
    RatelimitedPasswordResetView,
    RatelimitedSignupView,
    set_user_language,
)

urlpatterns = [
    re_path(r'^healthz/?$', healthz, name='healthz'),
    path(settings.ADMIN_URL, admin.site.urls),
    # Cambio de idioma: fija la cookie estándar de Django y, si hay sesión, la
    # preferencia en el perfil. Sin prefijos de idioma en las URLs.
    path('i18n/setlang/', set_user_language, name='set_language'),
    # SEO, bots y seguridad
    path('robots.txt', robots_txt, name='robots_txt'),
    path('sitemap.xml', sitemap_xml, name='sitemap_xml'),
    path('favicon.ico', favicon, name='favicon'),
    path('manifest.webmanifest', manifest_json, name='manifest_json'),
    path('offline/', offline_view, name='offline_fallback'),
    path('sw.js', service_worker, name='service_worker'),
    path('.well-known/security.txt', security_txt, name='security_txt'),
    path('.well-known/web-app-origin-association', web_app_origin_association, name='web_app_origin_association'),
    # Vistas de autenticación con rate limiting (prioritarias sobre allauth.urls)
    path('accounts/login/', RatelimitedLoginView.as_view(), name='account_login'),
    path('accounts/signup/', RatelimitedSignupView.as_view(), name='account_signup'),
    path('accounts/password/reset/', RatelimitedPasswordResetView.as_view(), name='account_reset_password'),
    re_path(
        r'^accounts/password/reset/key/(?P<uidb36>[0-9A-Za-z]+)-(?P<key>.+)/$',
        RatelimitedPasswordResetFromKeyView.as_view(),
        name='account_reset_password_from_key',
    ),
    path('accounts/', include('allauth.urls')),
    # Redirecciones 301 de las rutas legadas /videos/ a sus apps de dominio
    path('videos/', include('ilovevoley.videos.urls')),
    path('rosters/', include('ilovevoley.rosters.urls', namespace='rosters')),
    path('content/', include('ilovevoley.content.urls', namespace='content')),
    path('teams/', include('ilovevoley.teams.urls', namespace='teams')),
    path('competitions/', include('ilovevoley.competitions.urls', namespace='competitions')),
    path('competicion/', include('ilovevoley.competitions.portal_urls')),
    path('p/', include('ilovevoley.competitions.public_urls', namespace='public')),
    path('core/', include('ilovevoley.core.urls', namespace='core')),
    # Página pública "Sedes y pabellones" (sin login, acotada al tenant)
    path('donde-juega/', where_plays, name='where_plays'),
    path('donde-juega/buscar/', where_plays_search, name='where_plays_search'),
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
    from ilovevoley.core.views import test_400, test_403, test_404, test_429, test_500
    urlpatterns += [
        path('test-error/400/', test_400, name='test_400'),
        path('test-error/403/', test_403, name='test_403'),
        path('test-error/404/', test_404, name='test_404'),
        path('test-error/429/', test_429, name='test_429'),
        path('test-error/500/', test_500, name='test_500'),
    ]

# Custom error handlers
handler400 = 'ilovevoley.core.views.custom_400'
handler403 = 'ilovevoley.core.views.custom_403'
handler404 = 'ilovevoley.core.views.custom_404'
handler500 = 'ilovevoley.core.views.custom_500'
