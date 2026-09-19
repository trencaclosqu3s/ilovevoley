import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from videosvoley.core.tenant_utils import approve_user_membership, tenant_access_required
from ..forms import ImageModerationForm
from ..models import Image

logger = logging.getLogger(__name__)


def image_moderation(request):
    """Vista de moderación para admins"""
    images = Image.objects.select_related(
        'match__home_team', 'match__away_team', 'match__league',
        'uploaded_by'
    ).prefetch_related('categories').filter(status='pending').order_by('upload_date')
    
    # Paginación
    paginator = Paginator(images, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'pending_count': images.count(),
    }
    
    return render(request, 'videos/image_moderation.html', context)


@tenant_access_required(staff=True)
def image_moderate_action(request, image_id):
    """Acción de moderación individual"""
    image = get_object_or_404(Image, id=image_id, status='pending')
    
    if request.method == 'POST':
        form = ImageModerationForm(request.POST, instance=image)
        if form.is_valid():
            action = form.cleaned_data['action']
            notes = form.cleaned_data['moderation_notes']
            
            image.moderate(
                moderator=request.user,
                approved=(action == 'approve'),
                notes=notes
            )
            
            action_text = 'aprobada' if action == 'approve' else 'rechazada'
            messages.success(request, f'Imagen {action_text} correctamente.')
            return redirect('videos:image_moderation')
    else:
        form = ImageModerationForm()
    
    context = {
        'image': image,
        'form': form,
    }
    
    return render(request, 'videos/image_moderate.html', context)


@tenant_access_required(staff=True)
def image_moderate_bulk(request):
    """Moderación masiva de imágenes"""
    if request.method == 'POST':
        action = request.POST.get('action')
        image_ids = request.POST.getlist('image_ids')
        notes = request.POST.get('notes', '')
        
        if action in ['approve', 'reject'] and image_ids:
            images = Image.objects.filter(id__in=image_ids, status='pending')
            approved = (action == 'approve')
            
            for image in images:
                image.moderate(
                    moderator=request.user,
                    approved=approved,
                    notes=notes
                )
            
            action_text = 'aprobadas' if approved else 'rechazadas'
            messages.success(request, f'{images.count()} imágenes {action_text}.')
        
        return redirect('videos:image_moderation')
    
    return redirect('videos:image_moderation')


def moderation_counts_api(request):
    """API para obtener contadores de elementos pendientes de moderación"""
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
    
    return render(request, 'videos/moderation_panel.html', context)


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
                    subject=f'Actualización de tu solicitud en I Love Voley',
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


@login_required
@user_passes_test(lambda u: u.is_superuser, login_url='/')
@require_POST
def moderate_image_api(request, image_id):
    """API para moderar una imagen vía AJAX"""
    try:
        image = Image.objects.get(id=image_id, status='pending')
        action = request.POST.get('action')  # 'approve' o 'reject'
        notes = request.POST.get('notes', '')
        
        if action not in ['approve', 'reject']:
            return JsonResponse({
                'success': False,
                'error': 'Acción no válida'
            }, status=400)
        
        # Usar el método existente de moderación
        approved = (action == 'approve')
        image.moderate(
            moderator=request.user,
            approved=approved,
            notes=notes
        )
        
        action_text = 'aprobada' if approved else 'rechazada'
        
        return JsonResponse({
            'success': True,
            'message': f'Imagen "{image.title}" {action_text} correctamente',
            'image_title': image.title,
            'action': action
        })
        
    except Image.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Imagen no encontrada o ya moderada'
        }, status=404)
    except Exception as e:
        logger.error(f"Error moderando imagen {image_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Error interno del servidor'
        }, status=500)


__all__ = [
    'image_moderation',
    'image_moderate_action',
    'image_moderate_bulk',
    'moderation_counts_api',
    'moderation_panel',
    'approve_user_api',
    'reject_user_api',
    'moderate_image_api',
]
