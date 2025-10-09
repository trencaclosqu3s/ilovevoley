"""
Views for Calendar authorization and management, and custom error handlers.
"""
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from allauth.socialaccount.models import SocialAccount


@login_required
def request_calendar_permissions(request):
    """
    Redirect user to Google OAuth with Calendar permissions.
    """
    # Verificar si el usuario ya tiene cuenta Google conectada
    google_account = request.user.socialaccount_set.filter(provider='google').first()
    
    if not google_account:
        messages.error(request, 'Primero debes conectar tu cuenta de Google.')
        return redirect('socialaccount_connections')
    
    # Redirigir a OAuth con parámetro calendar=true para solicitar permisos de Calendar
    oauth_url = reverse('google_login') + '?calendar=true'
    return redirect(oauth_url)


@login_required  
def calendar_settings(request):
    """
    Mostrar configuración de Calendar sync para el usuario.
    """
    from allauth.socialaccount.models import SocialToken
    
    if request.method == 'POST':
        # Procesar cambios en configuración
        calendar_sync = request.POST.get('calendar_sync') == 'on'
        request.user.calendar_sync_enabled = calendar_sync
        request.user.save()
        
        if calendar_sync:
            messages.success(request, 'Sincronización de Calendar activada.')
        else:
            messages.info(request, 'Sincronización de Calendar desactivada.')
        
        return redirect('core:calendar_settings')
    
    # Verificar estado de permisos de Calendar
    google_account = request.user.socialaccount_set.filter(provider='google').first()
    has_google = bool(google_account)
    
    has_calendar_perms = False
    if google_account:
        # Probar directamente si el usuario puede acceder a Calendar
        from videosvoley.core.services.calendar_sync import get_calendar_service
        try:
            calendar_service = get_calendar_service(request.user)
            if calendar_service:
                has_calendar_perms = calendar_service.test_connection()
        except Exception:
            has_calendar_perms = False
    
    context = {
        'has_google': has_google,
        'has_calendar_perms': has_calendar_perms,
        'calendar_sync_enabled': request.user.calendar_sync_enabled,
    }
    
    return render(request, 'core/calendar_settings.html', context)


# Custom error handlers
def custom_400(request, exception=None):
    """
    Custom 400 Bad Request error page.
    """
    return render(request, '400.html', status=400)


def custom_403(request, exception=None):
    """
    Custom 403 Forbidden error page.
    """
    return render(request, '403.html', status=403)


def custom_404(request, exception=None):
    """
    Custom 404 Not Found error page.
    """
    return render(request, '404.html', status=404)


def custom_500(request):
    """
    Custom 500 Internal Server Error page.
    """
    return render(request, '500.html', status=500)


# Test views for error pages (only for development)
def test_400(request):
    """Test view for 400 error page."""
    return custom_400(request)


def test_403(request):
    """Test view for 403 error page."""
    return custom_403(request)


def test_404(request):
    """Test view for 404 error page."""
    return custom_404(request)


def test_500(request):
    """Test view for 500 error page."""
    return custom_500(request)