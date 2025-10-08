"""
URL configuration for videosvoley project.

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
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from django.contrib.auth.decorators import login_required
from videosvoley.core.moderation_views import moderate_user, moderate_image

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('videos/', include('videosvoley.videos.urls', namespace='videos')),
    path('core/', include('videosvoley.core.urls', namespace='core')),
    path('', include('videosvoley.users.urls')),
    # Rutas de moderación con tokens seguros
    path('moderate/user/<str:token>/', moderate_user, name='moderate_user'),
    path('moderate/image/<str:token>/', moderate_image, name='moderate_image'),
    path('', login_required(RedirectView.as_view(url='/videos/', permanent=False))),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # Test URLs para ver las páginas de error
    from videosvoley.core.views import test_400, test_403, test_404, test_500
    urlpatterns += [
        path('test-error/400/', test_400, name='test_400'),
        path('test-error/403/', test_403, name='test_403'),
        path('test-error/404/', test_404, name='test_404'),
        path('test-error/500/', test_500, name='test_500'),
    ]

# Custom error handlers
handler400 = 'videosvoley.core.views.custom_400'
handler403 = 'videosvoley.core.views.custom_403'
handler404 = 'videosvoley.core.views.custom_404'
handler500 = 'videosvoley.core.views.custom_500'
