"""
Core views: error handlers, landing, about, and user moderation.
"""
import logging
import os
from datetime import timedelta
from email.utils import parseaddr
from functools import lru_cache

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from ilovevoley.content.models import Image, ImageRemovalRequest
from ilovevoley.core.context_processors import DEFAULT_BRAND
from ilovevoley.core.forms import SeasonWizardForm
from ilovevoley.core.models import Organization, Season
from ilovevoley.core.services.season_wizard import preview_season, start_season
from ilovevoley.core.tenant_utils import (
    PWA_ORIGIN_ASSOCIATION_CACHE_KEY,
    approve_user_membership,
    build_absolute_url,
    build_tenant_url,
    can_moderate_images,
    get_tenant_base_domain,
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


def custom_429(request, exception=None):
    """
    Custom 429 Too Many Requests error page.
    Soporta HTML y respuestas JSON para peticiones AJAX o API.
    """
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    is_json = 'application/json' in request.headers.get('Accept', '') or request.content_type == 'application/json'
    is_api = '/api/' in request.path or request.path.startswith('/api/')
    if is_ajax or is_json or is_api:
        return JsonResponse({
            'error': _('Demasiadas peticiones'),
            'detail': _('Has superado el límite de intentos permitido. Por favor, espera un momento antes de volver a intentarlo.')
        }, status=429)
    return render(request, '429.html', status=429)


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


def test_429(request):
    """Test view for 429 error page."""
    return custom_429(request)


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

    user_organizations = []
    user_org_ids = set()

    if request.user.is_authenticated:
        from ilovevoley.users.models import Membership

        approved_memberships = list(
            Membership.objects.filter(
                user=request.user,
                is_approved=True,
                organization__is_active=True,
            ).select_related('organization').order_by('organization__name')
        )

        if len(approved_memberships) == 1:
            org = approved_memberships[0].organization
            target_url = build_tenant_url(org.slug, request)
            return redirect(target_url)

        if len(approved_memberships) > 1:
            user_organizations = [m.organization for m in approved_memberships]
            user_org_ids = {m.organization_id for m in approved_memberships}

    organizations = Organization.objects.filter(is_active=True).order_by('name')
    if user_organizations:
        other_organizations = organizations.exclude(id__in=user_org_ids)
    else:
        other_organizations = organizations

    return render(request, 'landing.html', {
        'organizations': organizations,
        'user_organizations': user_organizations,
        'other_organizations': other_organizations,
    })


def about(request):
    """Página 'Acerca de' con información del proyecto y del club"""
    context = {
        'title': 'Acerca de - Voleibol Sant Josep',
        'current_year': timezone.now().year,
    }
    return render(request, 'core/about.html', context)


def privacy_policy(request):
    """Página de política de privacidad (art. 13 RGPD) adaptada a la plataforma familiar."""
    contact_email = parseaddr(getattr(settings, 'PRIVACY_CONTACT_EMAIL', ''))[1]
    if not contact_email:
        contact_email = parseaddr(getattr(settings, 'DEFAULT_FROM_EMAIL', ''))[1] or 'privacidad@ilovevoley.es'
    context = {
        'privacy_email': contact_email,
        'current_year': timezone.now().year,
    }
    return render(request, 'core/privacy_policy.html', context)


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
    public_paths = [reverse('landing'), reverse('core:about'), reverse('core:privacy_policy')]
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


def manifest_json(request):
    """Devuelve el manifiesto W3C estandarizado para la PWA comunitaria I Love Voley."""
    tenant = getattr(request, 'tenant', None)
    theme_color = tenant.primary_color if tenant and tenant.primary_color else DEFAULT_BRAND
    base_domain = get_tenant_base_domain(request)
    protocol = 'https' if not settings.DEBUG else 'http'

    # Scope extensions para permitir navegación in-app entre tenants y dominio base
    if settings.DEBUG:
        active_slugs = Organization.objects.filter(is_active=True).values_list('slug', flat=True)
        scope_extensions = [{'origin': f'{protocol}://{base_domain}'}]
        for slug in active_slugs:
            scope_extensions.append({'origin': f'{protocol}://{slug}.{base_domain}'})
    else:
        scope_extensions = [
            {'origin': f'https://{base_domain}'},
            {'origin': f'https://*.{base_domain}'},
        ]


    manifest_data = {
        'id': '/',
        'name': 'I Love Voley',
        'short_name': 'ILoveVoley',
        'description': _('Plataforma comunitaria de gestión, vídeos y seguimiento de voleibol'),
        'lang': 'es',
        'dir': 'ltr',
        'start_url': '/',
        'scope': '/',
        'scope_extensions': scope_extensions,
        'display': 'standalone',
        'theme_color': theme_color,
        'background_color': '#ffffff',
        'icons': [
            {
                'src': static('images/icons/icon-192.png'),
                'sizes': '192x192',
                'type': 'image/png',
                'purpose': 'any',
            },
            {
                'src': static('images/icons/icon-512.png'),
                'sizes': '512x512',
                'type': 'image/png',
                'purpose': 'any',
            },
            {
                'src': static('images/icons/icon-maskable-512.png'),
                'sizes': '512x512',
                'type': 'image/png',
                'purpose': 'maskable',
            },
        ],
    }

    response = JsonResponse(manifest_data, content_type='application/manifest+json; charset=utf-8')
    response['Cache-Control'] = 'public, max-age=3600'
    response['Vary'] = 'Host'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def web_app_origin_association(request):
    """Devuelve la declaración de asociación de orígenes para PWA scope extensions."""
    protocol = 'https' if not settings.DEBUG else 'http'
    base_domain = get_tenant_base_domain(request)

    active_slugs = cache.get(PWA_ORIGIN_ASSOCIATION_CACHE_KEY)
    if active_slugs is None:
        active_slugs = list(
            Organization.objects.filter(is_active=True).values_list('slug', flat=True)
        )
        cache.set(PWA_ORIGIN_ASSOCIATION_CACHE_KEY, active_slugs, timeout=300)

    data = {
        f'{protocol}://{base_domain}/': {
            'scope': '/',
        },
        'web_apps': [
            {
                'manifest': '/manifest.webmanifest',
                'details': {
                    'paths': ['/*'],
                },
            }
        ],
    }
    for slug in active_slugs:
        data[f'{protocol}://{slug}.{base_domain}/'] = {
            'scope': '/',
        }

    response = JsonResponse(data, content_type='application/json; charset=utf-8')
    response['Cache-Control'] = 'public, max-age=86400'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def offline_view(request):
    """Página de fallback cuando el usuario no dispone de conexión a internet."""
    return render(request, 'offline.html', status=200)


@lru_cache(maxsize=1)
def _get_sw_content():
    sw_path = os.path.join(settings.BASE_DIR, 'ilovevoley', 'static', 'js', 'sw.js')
    with open(sw_path, 'r', encoding='utf-8') as f:
        return f.read()


def service_worker(request):
    """Sirve el archivo sw.js desde la raíz con cabeceras de Service Worker."""
    if settings.DEBUG:
        sw_path = os.path.join(settings.BASE_DIR, 'ilovevoley', 'static', 'js', 'sw.js')
        with open(sw_path, 'r', encoding='utf-8') as f:
            content = f.read()
    else:
        content = _get_sw_content()
    response = HttpResponse(content, content_type='application/javascript; charset=utf-8')
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


def _can_moderate_memberships(request):
    """True si el usuario es superuser o manager/admin aprobado del tenant actual."""
    return user_is_tenant_manager(request.user, getattr(request, 'tenant', None))


def _get_pending_membership(user_id, tenant):
    """Devuelve la Membership pendiente del usuario en el tenant o lanza DoesNotExist."""
    return Membership.objects.select_related('user').get(
        user_id=user_id, organization=tenant, is_approved=False
    )


def _reactivation_requests_qs(request):
    """Solicitudes de reactivación visibles para quien modera (#327).

    En un club se limita a las cuentas con membresía en ese tenant; sin tenant,
    solo el superusuario ve el conjunto global. Un gestor de club nunca ve
    solicitudes de usuarios de otros clubes.
    """
    User = get_user_model()
    tenant = getattr(request, 'tenant', None)
    qs = User.objects.filter(reactivation_requested_at__isnull=False)
    if tenant:
        qs = qs.filter(memberships__organization=tenant).distinct()
    elif not request.user.is_superuser:
        return User.objects.none()
    return qs.order_by('reactivation_requested_at')


def moderation_counts_api(request):
    """API para obtener contadores de elementos pendientes de moderación"""
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': _('No autenticado')}, status=401)
    if not _can_moderate_memberships(request):
        return JsonResponse({'success': False, 'error': _('Permiso denegado')}, status=403)

    User = get_user_model()
    tenant = getattr(request, 'tenant', None)

    if tenant:
        pending_users_count = User.objects.filter(
            is_active=True,
            memberships__organization=tenant,
            memberships__is_approved=False,
        ).distinct().count()
    elif request.user.is_superuser:
        # Pendiente = sin aprobar y activo. Un usuario rechazado se desactiva
        # (is_active=False) manteniendo is_approved=False, así que no cuenta.
        pending_users_count = User.objects.filter(
            is_approved=False, is_active=True
        ).count()
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

    # Convocatorias dudosas pendientes de moderación
    from ilovevoley.competitions.models import CallUpPlayer

    if tenant:
        pending_callups_count = CallUpPlayer.objects.filter(
            organization=tenant, match_status='suspected'
        ).count()
    elif request.user.is_superuser:
        pending_callups_count = CallUpPlayer.objects.filter(
            match_status='suspected'
        ).count()
    else:
        pending_callups_count = 0

    # Solicitudes de retirada de fotos (solo relevante para quien modera imágenes)
    if can_mod_images:
        if tenant:
            pending_removals_count = ImageRemovalRequest.objects.filter(
                organization=tenant, status='pending'
            ).count()
        elif request.user.is_superuser:
            pending_removals_count = ImageRemovalRequest.objects.filter(status='pending').count()
        else:
            pending_removals_count = 0
    else:
        pending_removals_count = 0

    # Total de elementos pendientes
    pending_reactivations_count = _reactivation_requests_qs(request).count()
    total_pending = (
        pending_users_count + pending_images_count + pending_callups_count
        + pending_reactivations_count + pending_removals_count
    )

    return JsonResponse({
        'success': True,
        'pending_users': pending_users_count,
        'pending_images': pending_images_count,
        'pending_callups': pending_callups_count,
        'pending_reactivations': pending_reactivations_count,
        'pending_removals': pending_removals_count,
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
            is_active=True,
            memberships__organization=tenant,
            memberships__is_approved=False,
        ).distinct().order_by('date_joined')
    elif is_superuser:
        # Igual que en el contador: se excluyen las cuentas desactivadas, que
        # son las rechazadas, para que el rechazo persista al refrescar.
        pending_users = User.objects.filter(
            is_approved=False, is_active=True
        ).order_by('date_joined')
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

    from ilovevoley.competitions.models import CallUpPlayer

    if tenant:
        pending_callups = CallUpPlayer.objects.filter(
            organization=tenant, match_status='suspected'
        ).select_related('callup', 'person').order_by('-callup__circular_date', '-callup__id')
    elif is_superuser:
        pending_callups = CallUpPlayer.objects.filter(
            match_status='suspected'
        ).select_related('callup', 'person', 'organization').order_by('-callup__circular_date', '-callup__id')
    else:
        pending_callups = CallUpPlayer.objects.none()

    if can_mod_images:
        if tenant:
            pending_removals = ImageRemovalRequest.objects.filter(
                organization=tenant, status='pending'
            ).select_related('image', 'person', 'requested_by').order_by('created_at')
        elif is_superuser:
            pending_removals = ImageRemovalRequest.objects.filter(
                status='pending'
            ).select_related('image', 'person', 'requested_by', 'organization').order_by('created_at')
        else:
            pending_removals = ImageRemovalRequest.objects.none()
    else:
        pending_removals = ImageRemovalRequest.objects.none()

    reactivation_users = _reactivation_requests_qs(request)
    context = {
        'pending_users': pending_users,
        'pending_images': pending_images,
        'pending_callups': pending_callups,
        'pending_removals': pending_removals,
        'reactivation_users': reactivation_users,
        'pending_users_count': pending_users.count(),
        'pending_images_count': pending_images.count(),
        'pending_callups_count': pending_callups.count(),
        'pending_removals_count': pending_removals.count(),
        'pending_reactivations_count': reactivation_users.count(),
        'can_moderate_images': can_mod_images,
    }

    return render(request, 'core/moderation_panel.html', context)


@login_required
@require_POST
def approve_user_api(request, user_id):
    """API para aprobar un usuario vía AJAX (superuser o manager del tenant)"""
    if not _can_moderate_memberships(request):
        return JsonResponse({'success': False, 'error': _('Permiso denegado')}, status=403)

    User = get_user_model()
    tenant = getattr(request, 'tenant', None)

    try:
        if tenant is None and request.user.is_superuser:
            user = User.objects.get(id=user_id, is_approved=False, is_active=True)
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
            'message': _('Usuario %(username)s aprobado correctamente') % {'username': user.username},
            'user_name': user.username
        })

    except (User.DoesNotExist, Membership.DoesNotExist):
        return JsonResponse({
            'success': False,
            'error': _('Usuario no encontrado o ya aprobado')
        }, status=404)
    except Exception as e:
        logger.error(f"Error aprobando usuario {user_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': _('Error interno del servidor')
        }, status=500)


@login_required
@require_POST
def reject_user_api(request, user_id):
    """API para rechazar un usuario vía AJAX (superuser o manager del tenant)"""
    if not _can_moderate_memberships(request):
        return JsonResponse({'success': False, 'error': _('Permiso denegado')}, status=403)

    User = get_user_model()
    tenant = getattr(request, 'tenant', None)

    try:
        if request.user.is_superuser:
            if tenant is None:
                user = User.objects.get(id=user_id, is_approved=False, is_active=True)
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
            'message': _('Usuario %(username)s rechazado correctamente') % {'username': user.username},
            'user_name': user.username
        })

    except (User.DoesNotExist, Membership.DoesNotExist):
        return JsonResponse({
            'success': False,
            'error': _('Usuario no encontrado o ya procesado')
        }, status=404)
    except Exception as e:
        logger.error(f"Error rechazando usuario {user_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': _('Error interno del servidor')
        }, status=500)


@login_required
@require_POST
def resolve_image_removal(request, request_id):
    """Resuelve una solicitud de retirada de foto: elimina la imagen o la descarta."""
    tenant = getattr(request, 'tenant', None)
    if not can_moderate_images(request.user, tenant):
        raise PermissionDenied

    removal = ImageRemovalRequest.objects.filter(id=request_id, status='pending').first()
    if removal is None:
        messages.error(request, _('La solicitud ya no está pendiente.'))
        return redirect('core:moderation_panel')

    if tenant is not None and removal.organization_id != tenant.id and not request.user.is_superuser:
        raise PermissionDenied

    action = request.POST.get('action')
    removal.resolved_at = timezone.now()
    removal.resolved_by = request.user

    if action == 'remove':
        if removal.image is not None:
            from ilovevoley.content.services import delete_image_with_files

            delete_image_with_files(removal.image)
            removal.image = None
        removal.status = 'removed'
        messages.success(request, _('Foto eliminada.'))
    elif action == 'dismiss':
        removal.status = 'dismissed'
        messages.success(request, _('Solicitud descartada.'))
    else:
        messages.error(request, _('Acción no válida.'))
        return redirect('core:moderation_panel')

    removal.save(update_fields=['status', 'resolved_at', 'resolved_by'])
    return redirect('core:moderation_panel')


def _get_reactivation_user(request, user_id):
    """Cuenta con solicitud de reactivación que el moderador actual puede gestionar."""
    User = get_user_model()
    tenant = getattr(request, 'tenant', None)
    qs = User.objects.filter(id=user_id, reactivation_requested_at__isnull=False)
    if tenant:
        qs = qs.filter(memberships__organization=tenant)
    elif not request.user.is_superuser:
        qs = qs.none()
    return qs.distinct().get()


@login_required
@require_POST
def reactivate_user_api(request, user_id):
    """Reactiva una cuenta desactivada tras aprobar su solicitud de vuelta (#327)."""
    if not _can_moderate_memberships(request):
        return JsonResponse({'success': False, 'error': _('Permiso denegado')}, status=403)

    User = get_user_model()
    tenant = getattr(request, 'tenant', None)
    try:
        user = _get_reactivation_user(request, user_id)
        approve_user_membership(user, tenant=tenant)
        user.reactivation_requested_at = None
        user.inactivity_warning_level = 0
        user.inactivity_warning_sent_at = None
        user.save(update_fields=[
            'reactivation_requested_at',
            'inactivity_warning_level',
            'inactivity_warning_sent_at',
        ])
        return JsonResponse({
            'success': True,
            'message': _('Usuario %(username)s reactivado correctamente') % {'username': user.username},
            'user_name': user.username,
        })
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': _('Solicitud no encontrada')}, status=404)
    except Exception as e:
        logger.error(f"Error reactivando usuario {user_id}: {str(e)}")
        return JsonResponse({'success': False, 'error': _('Error interno del servidor')}, status=500)


@login_required
@require_POST
def dismiss_reactivation_api(request, user_id):
    """Descarta la solicitud de reactivación; la cuenta sigue desactivada (#327)."""
    if not _can_moderate_memberships(request):
        return JsonResponse({'success': False, 'error': _('Permiso denegado')}, status=403)

    User = get_user_model()
    try:
        user = _get_reactivation_user(request, user_id)
        user.reactivation_requested_at = None
        user.save(update_fields=['reactivation_requested_at'])
        return JsonResponse({
            'success': True,
            'message': _('Solicitud de %(username)s descartada') % {'username': user.username},
            'user_name': user.username,
        })
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': _('Solicitud no encontrada')}, status=404)
    except Exception as e:
        logger.error(f"Error descartando reactivación de {user_id}: {str(e)}")
        return JsonResponse({'success': False, 'error': _('Error interno del servidor')}, status=500)


@login_required
@require_POST
def confirm_callup_api(request, player_id):
    """API para confirmar una convocatoria dudosa vía AJAX."""
    if not _can_moderate_memberships(request):
        return JsonResponse({'success': False, 'error': _('Permiso denegado')}, status=403)

    tenant = getattr(request, 'tenant', None)
    from ilovevoley.competitions.models import CallUpPlayer
    from ilovevoley.competitions.services.notifications import notify_callup_confirmed

    try:
        if tenant:
            player = CallUpPlayer.objects.select_related('callup', 'organization', 'person').get(
                id=player_id, organization=tenant
            )
        elif request.user.is_superuser:
            player = CallUpPlayer.objects.select_related('callup', 'organization', 'person').get(
                id=player_id
            )
        else:
            return JsonResponse({'success': False, 'error': _('Permiso denegado')}, status=403)
    except CallUpPlayer.DoesNotExist:
        return JsonResponse({'success': False, 'error': _('Jugador convocado no encontrado')}, status=404)

    player.match_status = CallUpPlayer.STATUS_CONFIRMED
    player.reviewed_by = request.user
    player.reviewed_at = timezone.now()
    player.save(update_fields=['match_status', 'reviewed_by', 'reviewed_at'])

    notify_callup_confirmed(player)

    return JsonResponse({'success': True, 'player_id': player.id, 'match_status': 'confirmed'})


@login_required
@require_POST
def reject_callup_api(request, player_id):
    """API para descartar una convocatoria dudosa vía AJAX."""
    if not _can_moderate_memberships(request):
        return JsonResponse({'success': False, 'error': _('Permiso denegado')}, status=403)

    tenant = getattr(request, 'tenant', None)
    from ilovevoley.competitions.models import CallUpPlayer

    try:
        if tenant:
            player = CallUpPlayer.objects.get(id=player_id, organization=tenant)
        elif request.user.is_superuser:
            player = CallUpPlayer.objects.get(id=player_id)
        else:
            return JsonResponse({'success': False, 'error': _('Permiso denegado')}, status=403)
    except CallUpPlayer.DoesNotExist:
        return JsonResponse({'success': False, 'error': _('Jugador convocado no encontrado')}, status=404)

    player.match_status = CallUpPlayer.STATUS_REJECTED
    player.reviewed_by = request.user
    player.reviewed_at = timezone.now()
    player.save(update_fields=['match_status', 'reviewed_by', 'reviewed_at'])

    return JsonResponse({'success': True, 'player_id': player.id, 'match_status': 'rejected'})


def _require_superuser(request):
    """El wizard de temporada es de plataforma: solo superusers."""
    if not request.user.is_superuser:
        raise PermissionDenied


@login_required
def season_wizard(request):
    """Paso 1: formulario con el nombre de la nueva temporada."""
    _require_superuser(request)

    if request.method == 'POST':
        form = SeasonWizardForm(request.POST)
        if form.is_valid():
            confirm_url = reverse('core:season_wizard_confirm')
            return redirect(f'{confirm_url}?name={form.cleaned_data["name"]}')
    else:
        form = SeasonWizardForm()

    return render(request, 'core/season_wizard.html', {
        'form': form,
        'current_season': Season.objects.current(),
    })


@login_required
def season_wizard_confirm(request):
    """Paso 2: resumen/dry-run (GET) y aplicación atómica (POST)."""
    _require_superuser(request)

    raw = request.POST.get('name') or request.GET.get('name') or ''
    summary = preview_season(raw)
    if not summary['valid']:
        messages.error(request, _('Formato de temporada no válido.'))
        return redirect('core:season_wizard')

    if request.method == 'POST':
        summary = start_season(raw)
        messages.success(
            request,
            _('Temporada %(name)s activada (%(count)s liga(s) archivada(s)).') % {
                'name': summary["season"].name,
                'count': summary["archived_leagues"],
            },
        )
        return redirect('core:season_wizard')

    return render(request, 'core/season_wizard_confirm.html', {'summary': summary})


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
    'manifest_json',
    'offline_view',
    'service_worker',
    'moderation_counts_api',
    'moderation_panel',
    'approve_user_api',
    'reject_user_api',
    'season_wizard',
    'season_wizard_confirm',
]
