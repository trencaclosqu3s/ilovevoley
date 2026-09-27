"""
Core views: error handlers, landing, about, and user moderation.
"""
import logging
from datetime import timedelta
from email.utils import parseaddr

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from ilovevoley.content.models import Image
from ilovevoley.core.tenant_utils import (
    approve_user_membership,
    build_absolute_url,
    can_moderate_images,
    reject_user_membership,
    user_is_tenant_manager,
)
from ilovevoley.users.models import Membership

logger = logging.getLogger(__name__)


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


def landing(request):
    """
    Landing page for root domain with organization selection.
    On tenant domains: login if anonymous, configured homepage if authenticated.
    """
    from django.shortcuts import redirect
    from django.urls import reverse
    from ilovevoley.core.models import Organization

    if request.tenant:
        home_url_name = request.tenant.home_url_name
        if request.user.is_authenticated:
            return redirect(home_url_name)
        login_url = reverse('account_login')
        next_url = reverse(home_url_name)
        return redirect(f'{login_url}?next={next_url}')

    organizations = Organization.objects.filter(is_active=True).order_by('name')

    user_org_ids = set()
    if request.user.is_authenticated:
        from ilovevoley.users.models import Membership
        user_org_ids = set(
            Membership.objects.filter(
                user=request.user, is_approved=True
            ).values_list('organization_id', flat=True)
        )

    return render(request, 'landing.html', {
        'organizations': organizations,
        'user_org_ids': user_org_ids,
    })


def about(request):
    """Página 'Acerca de' con información del proyecto y del club"""
    context = {
        'title': 'Acerca de - Voleibol Sant Josep',
        'current_year': timezone.now().year,
    }
    return render(request, 'core/about.html', context)


def healthz(request):
    """
    Health check endpoint for deployment validation and uptime monitoring.
    Verifies database connectivity.
    """
    from django.db import connection

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({'status': 'ok'}, status=200)
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JsonResponse({'status': 'error'}, status=503)


def robots_txt(request):
    """robots.txt: permite la landing pública y bloquea rutas privadas."""
    admin_path = '/' + settings.ADMIN_URL.strip('/') + '/'
    lines = [
        'User-agent: *',
        f'Disallow: {admin_path}',
        'Disallow: /accounts/',
        'Disallow: /media/',
        'Disallow: /moderate/',
        'Disallow: /core/moderacion/',
        'Disallow: /core/api/',
        'Disallow: /videos/calendario/suscripcion/',
        'Disallow: /competitions/calendario/suscripcion/',
        'Allow: /',
        f'Sitemap: {build_absolute_url(reverse("sitemap_xml"), request=request)}',
    ]
    return HttpResponse('\n'.join(lines) + '\n', content_type='text/plain; charset=utf-8')


def sitemap_xml(request):
    """Sitemap con las páginas públicas informativas (sin contenido de club)."""
    public_paths = [reverse('landing'), reverse('core:about')]
    urls = ''.join(
        f'  <url><loc>{build_absolute_url(path, request=request)}</loc></url>\n'
        for path in public_paths
    )
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'{urls}'
        '</urlset>\n'
    )
    return HttpResponse(content, content_type='application/xml; charset=utf-8')


def favicon(request):
    """Redirige /favicon.ico al icono SVG declarado en las plantillas."""
    return redirect(static('images/favicon.svg'), permanent=True)


def security_txt(request):
    """security.txt con el contacto de seguridad y caducidad a un año."""
    contact = parseaddr(settings.SECURITY_CONTACT_EMAIL)[1]
    if not contact:
        contact = parseaddr(settings.DEFAULT_FROM_EMAIL)[1]
    expires = (timezone.now() + timedelta(days=365)).strftime('%Y-%m-%dT%H:%M:%SZ')
    lines = [
        f'Contact: mailto:{contact}',
        f'Expires: {expires}',
        'Preferred-Languages: es, en',
        f'Canonical: {build_absolute_url(reverse("security_txt"), request=request)}',
    ]
    return HttpResponse('\n'.join(lines) + '\n', content_type='text/plain; charset=utf-8')

def _can_moderate_memberships(request):
    """True si el usuario es superuser o manager/admin aprobado del tenant actual."""
    return user_is_tenant_manager(request.user, getattr(request, 'tenant', None))


def _get_pending_membership(user_id, tenant):
    """Devuelve la Membership pendiente del usuario en el tenant o lanza DoesNotExist."""
    return Membership.objects.select_related('user').get(
        user_id=user_id, organization=tenant, is_approved=False
    )


def moderation_counts_api(request):
    """API para obtener contadores de elementos pendientes de moderación"""
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'No autenticado'}, status=401)
    if not _can_moderate_memberships(request):
        return JsonResponse({'success': False, 'error': 'Permiso denegado'}, status=403)

    User = get_user_model()
    tenant = getattr(request, 'tenant', None)

    if tenant:
        pending_users_count = User.objects.filter(
            memberships__organization=tenant,
            memberships__is_approved=False,
        ).distinct().count()
    elif request.user.is_superuser:
        pending_users_count = User.objects.filter(is_approved=False).count()
    else:
        pending_users_count = 0

    # Imágenes pendientes según permisos y alcance (tenant o global)
    can_mod_images = can_moderate_images(request.user, tenant)
    if can_mod_images:
        if tenant:
            pending_images_count = Image.objects.filter(
                organization=tenant, status='pending'
            ).count()
        elif request.user.is_superuser:
            pending_images_count = Image.objects.filter(status='pending').count()
        else:
            pending_images_count = 0
    else:
        pending_images_count = 0

    # Total de elementos pendientes
    total_pending = pending_users_count + pending_images_count

    return JsonResponse({
        'success': True,
        'pending_users': pending_users_count,
        'pending_images': pending_images_count,
        'total_pending': total_pending
    })


@login_required
def moderation_panel(request):
    """Panel de moderación para superusers y managers/admins del tenant actual."""
    if not _can_moderate_memberships(request):
        raise PermissionDenied

    User = get_user_model()
    tenant = getattr(request, 'tenant', None)
    is_superuser = request.user.is_superuser

    if tenant:
        pending_users = User.objects.filter(
            memberships__organization=tenant,
            memberships__is_approved=False,
        ).distinct().order_by('date_joined')
    elif is_superuser:
        pending_users = User.objects.filter(is_approved=False).order_by('date_joined')
    else:
        pending_users = User.objects.none()

    # Las imágenes pendientes se acotan al tenant o al ámbito global según permisos
    can_mod_images = can_moderate_images(request.user, tenant)
    if can_mod_images:
        if tenant:
            pending_images = Image.objects.filter(
                organization=tenant, status='pending'
            ).select_related(
                'uploaded_by', 'match__home_team', 'match__away_team', 'match__league'
            ).prefetch_related('categories').order_by('upload_date')
        elif is_superuser:
            pending_images = Image.objects.filter(status='pending').select_related(
                'uploaded_by', 'match__home_team', 'match__away_team', 'match__league'
            ).prefetch_related('categories').order_by('upload_date')
        else:
            pending_images = Image.objects.none()
    else:
        pending_images = Image.objects.none()

    context = {
        'pending_users': pending_users,
        'pending_images': pending_images,
        'pending_users_count': pending_users.count(),
        'pending_images_count': pending_images.count(),
        'can_moderate_images': can_mod_images,
    }

    return render(request, 'core/moderation_panel.html', context)


@login_required
@require_POST
def approve_user_api(request, user_id):
    """API para aprobar un usuario vía AJAX (superuser o manager del tenant)"""
    if not _can_moderate_memberships(request):
        return JsonResponse({'success': False, 'error': 'Permiso denegado'}, status=403)

    User = get_user_model()
    tenant = getattr(request, 'tenant', None)

    try:
        if tenant is None and request.user.is_superuser:
            user = User.objects.get(id=user_id, is_approved=False)
        else:
            user = _get_pending_membership(user_id, tenant).user

        approve_user_membership(user, tenant)

        # Enviar email de confirmación si está configurado
        if getattr(settings, 'NOTIFICATION_EMAIL_ENABLED', False) and user.email:
            try:
                from ilovevoley.core.email_utils import enqueue_on_commit
                from ilovevoley.core.tasks import notify_user_moderation_result_task
                enqueue_on_commit(notify_user_moderation_result_task, user.id, True)
            except Exception as e:
                logger.warning(f"Error encolando email de aprobación: {e}")

        return JsonResponse({
            'success': True,
            'message': f'Usuario {user.username} aprobado correctamente',
            'user_name': user.username
        })

    except (User.DoesNotExist, Membership.DoesNotExist):
        return JsonResponse({
            'success': False,
            'error': 'Usuario no encontrado o ya aprobado'
        }, status=404)
    except Exception as e:
        logger.error(f"Error aprobando usuario {user_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Error interno del servidor'
        }, status=500)


@login_required
@require_POST
def reject_user_api(request, user_id):
    """API para rechazar un usuario vía AJAX (superuser o manager del tenant)"""
    if not _can_moderate_memberships(request):
        return JsonResponse({'success': False, 'error': 'Permiso denegado'}, status=403)

    User = get_user_model()
    tenant = getattr(request, 'tenant', None)

    try:
        if request.user.is_superuser:
            if tenant is None:
                user = User.objects.get(id=user_id, is_approved=False)
            else:
                user = _get_pending_membership(user_id, tenant).user
            # Rechazar = desactivar el usuario y mantener is_approved en False
            user.is_active = False
            user.save(update_fields=['is_active'])
        else:
            # El manager/admin del club solo deniega la membresía de su organización:
            # la cuenta global del usuario no se toca.
            user = _get_pending_membership(user_id, tenant).user
            reject_user_membership(user, tenant)

        # Enviar email de rechazo si está configurado
        if getattr(settings, 'NOTIFICATION_EMAIL_ENABLED', False) and user.email:
            try:
                from ilovevoley.core.email_utils import enqueue_on_commit
                from ilovevoley.core.tasks import notify_user_moderation_result_task
                enqueue_on_commit(notify_user_moderation_result_task, user.id, False)
            except Exception as e:
                logger.warning(f"Error encolando email de rechazo: {e}")

        return JsonResponse({
            'success': True,
            'message': f'Usuario {user.username} rechazado correctamente',
            'user_name': user.username
        })

    except (User.DoesNotExist, Membership.DoesNotExist):
        return JsonResponse({
            'success': False,
            'error': 'Usuario no encontrado o ya procesado'
        }, status=404)
    except Exception as e:
        logger.error(f"Error rechazando usuario {user_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Error interno del servidor'
        }, status=500)


__all__ = [
    'custom_400',
    'custom_403',
    'custom_404',
    'custom_500',
    'test_400',
    'test_403',
    'test_404',
    'test_500',
    'landing',
    'about',
    'healthz',
    'robots_txt',
    'sitemap_xml',
    'favicon',
    'security_txt',
    'moderation_counts_api',
    'moderation_panel',
    'approve_user_api',
    'reject_user_api',
]