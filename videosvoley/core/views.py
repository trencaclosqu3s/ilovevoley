"""
Core views: error handlers, landing, about, and user moderation.
"""
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST

from videosvoley.content.models import Image
from videosvoley.core.tenant_utils import approve_user_membership

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
    On tenant domains: login if anonymous, /videos/ if authenticated.
    """
    from django.shortcuts import redirect
    from django.urls import reverse
    from videosvoley.core.models import Organization

    if request.tenant:
        if request.user.is_authenticated:
            return redirect('content:video_list')
        login_url = reverse('account_login')
        next_url = reverse('content:video_list')
        return redirect(f'{login_url}?next={next_url}')

    organizations = Organization.objects.filter(is_active=True).order_by('name')

    user_org_ids = set()
    if request.user.is_authenticated:
        from videosvoley.users.models import Membership
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


def moderation_counts_api(request):
    """API para obtener contadores de elementos pendientes de moderación"""
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'No autenticado'}, status=401)
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'error': 'Permiso denegado'}, status=403)
    User = get_user_model()

    if getattr(request, 'tenant', None):
        pending_users = User.objects.filter(
            memberships__organization=request.tenant,
            memberships__is_approved=False,
        ).distinct().order_by('date_joined')
        pending_users_count = pending_users.count()
    else:
        pending_users_count = User.objects.filter(is_approved=False).count()

    # Contar imágenes pendientes de moderación
    pending_images_count = Image.objects.filter(status='pending').count()

    # Total de elementos pendientes
    total_pending = pending_users_count + pending_images_count

    return JsonResponse({
        'success': True,
        'pending_users': pending_users_count,
        'pending_images': pending_images_count,
        'total_pending': total_pending
    })


@login_required
@user_passes_test(lambda u: u.is_superuser, login_url='/')
def moderation_panel(request):
    """Panel de moderación simplificado para superusers"""
    User = get_user_model()

    if getattr(request, 'tenant', None):
        pending_users = User.objects.filter(
            memberships__organization=request.tenant,
            memberships__is_approved=False,
        ).distinct().order_by('date_joined')
    else:
        pending_users = User.objects.filter(is_approved=False).order_by('date_joined')

    # Obtener imágenes pendientes de moderación
    pending_images = Image.objects.filter(status='pending').select_related(
        'uploaded_by', 'match__home_team', 'match__away_team', 'match__league'
    ).prefetch_related('categories').order_by('upload_date')

    context = {
        'pending_users': pending_users,
        'pending_images': pending_images,
        'pending_users_count': pending_users.count(),
        'pending_images_count': pending_images.count(),
    }

    return render(request, 'core/moderation_panel.html', context)


@login_required
@user_passes_test(lambda u: u.is_superuser, login_url='/')
@require_POST
def approve_user_api(request, user_id):
    """API para aprobar un usuario vía AJAX"""
    User = get_user_model()

    try:
        user = User.objects.get(id=user_id, is_approved=False)
        approve_user_membership(user, getattr(request, 'tenant', None))

        # Enviar email de confirmación si está configurado
        if getattr(settings, 'NOTIFICATION_EMAIL_ENABLED', False):
            try:
                from videosvoley.core.email_utils import send_notification_email
                send_notification_email(
                    subject=f'Usuario aprobado - {user.username}',
                    template_name='emails/user_approved.html',
                    context={'user': user},
                    recipient_list=[user.email] if user.email else []
                )
            except Exception as e:
                logger.warning(f"Error enviando email de aprobación: {e}")

        return JsonResponse({
            'success': True,
            'message': f'Usuario {user.username} aprobado correctamente',
            'user_name': user.username
        })

    except User.DoesNotExist:
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
@user_passes_test(lambda u: u.is_superuser, login_url='/')
@require_POST
def reject_user_api(request, user_id):
    """API para rechazar un usuario vía AJAX"""
    User = get_user_model()

    try:
        user = User.objects.get(id=user_id, is_approved=False)
        # Rechazar = desactivar el usuario y mantener is_approved en False
        user.is_active = False
        user.save(update_fields=['is_active'])

        # Enviar email de rechazo si está configurado
        if getattr(settings, 'NOTIFICATION_EMAIL_ENABLED', False):
            try:
                from videosvoley.core.email_utils import send_notification_email
                send_notification_email(
                    subject='Actualización de tu solicitud en I Love Voley',
                    template_name='emails/user_rejected.html',
                    context={
                        'user': user,
                        'site_name': 'I Love Voley',
                    },
                    recipient_list=[user.email] if user.email else []
                )
            except Exception as e:
                logger.warning(f"Error enviando email de rechazo: {e}")

        return JsonResponse({
            'success': True,
            'message': f'Usuario {user.username} rechazado correctamente',
            'user_name': user.username
        })

    except User.DoesNotExist:
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
    'moderation_counts_api',
    'moderation_panel',
    'approve_user_api',
    'reject_user_api',
]