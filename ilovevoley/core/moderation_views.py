"""
Vistas para moderación segura con tokens (requiere login y confirmación por POST)
"""
import secrets
from collections import namedtuple

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.http import HttpResponseBadRequest, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from ilovevoley.content.models import Image
from ilovevoley.core.email_utils import send_notification_email
from ilovevoley.core.image_utils import image_to_data_uri
from ilovevoley.core.models import Organization
from ilovevoley.core.tenant_utils import (
    approve_user_membership,
    build_absolute_url,
    reject_user_membership,
    user_is_tenant_manager,
    user_is_tenant_staff,
)

User = get_user_model()

MODERATION_SALT = "ilovevoley.moderation.v1"
# Token expira en 60 minutos (configurable en settings con fallback de 3600 segundos)
TOKEN_MAX_AGE = getattr(settings, 'MODERATION_TOKEN_MAX_AGE', 3600)

ModerationTokenData = namedtuple(
    'ModerationTokenData',
    ['item_type', 'item_id', 'action', 'tenant_id', 'nonce']
)


def _token_cache_key(nonce):
    return f"moderation_token_consumed:{nonce}"


def is_token_consumed(nonce):
    """Comprueba si un nonce ya ha sido consumido."""
    if not nonce:
        return False
    return cache.get(_token_cache_key(nonce)) is not None


def mark_token_consumed(nonce, max_age=TOKEN_MAX_AGE):
    """
    Marca un token como consumido de forma atómica en cache.
    Retorna True si se marcó por primera vez, o False si ya existía.
    """
    if not nonce:
        return True
    key = _token_cache_key(nonce)
    return bool(cache.add(key, True, timeout=max_age))


def generate_moderation_token(item_type, item_id, action, tenant_id=None):
    """
    Genera un token seguro y de un solo uso para moderación.
    
    Args:
        item_type: 'user' o 'image'
        item_id: ID del usuario o imagen
        action: 'approve' o 'reject'
        tenant_id: ID o instancia de Organization (opcional)
    
    Returns:
        str: Token firmado
    """
    if hasattr(tenant_id, 'id'):
        tenant_id = tenant_id.id
    tenant_str = str(tenant_id) if tenant_id else ''
    nonce = secrets.token_hex(16)
    value = f"{item_type}:{item_id}:{action}:{tenant_str}:{nonce}"
    signer = TimestampSigner(salt=MODERATION_SALT)
    return signer.sign(value)


def verify_moderation_token(token, max_age=None, check_consumed=True):
    """
    Verifica un token de moderación.
    
    Args:
        token: Token a verificar
        max_age: Edad máxima del token en segundos (por defecto TOKEN_MAX_AGE)
        check_consumed: Si True, verifica que el nonce no haya sido consumido ya
    
    Returns:
        ModerationTokenData o None si es inválido/expirado/consumido
    """
    if max_age is None:
        import ilovevoley.core.moderation_views as mod_views
        max_age = mod_views.TOKEN_MAX_AGE

    try:
        signer = TimestampSigner(salt=MODERATION_SALT)
        value = signer.unsign(token, max_age=max_age)
        parts = value.split(':')
        if len(parts) == 5:
            item_type, item_id, action, tenant_str, nonce = parts
            if check_consumed and is_token_consumed(nonce):
                return None
            tenant_id = int(tenant_str) if tenant_str else None
            return ModerationTokenData(
                item_type=item_type,
                item_id=int(item_id),
                action=action,
                tenant_id=tenant_id,
                nonce=nonce
            )
        elif len(parts) == 3:
            item_type, item_id, action = parts
            return ModerationTokenData(
                item_type=item_type,
                item_id=int(item_id),
                action=action,
                tenant_id=None,
                nonce=''
            )
    except (BadSignature, SignatureExpired, ValueError):
        pass
    return None


def can_moderate(user, item_type, item, tenant=None):
    """
    Comprueba si el usuario autenticado tiene permisos para moderar el recurso.
    Requiere ser superuser o tener rol staff/manager en el tenant afectado.
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if tenant is not None:
        return user_is_tenant_manager(user, tenant) or user_is_tenant_staff(user, tenant)
    return user.is_staff


@login_required
def moderate_user(request, token):
    """
    Vista para aprobar/rechazar usuario mediante token seguro.
    GET muestra formulario de confirmación con CSRF.
    POST ejecuta la acción de forma idempotente y consume el token.
    """
    if request.method not in ['GET', 'POST']:
        return HttpResponseNotAllowed(['GET', 'POST'])

    token_data = verify_moderation_token(token, check_consumed=False)
    if not token_data or token_data.item_type != 'user':
        return render(request, 'moderation_result.html', {
            'success': False,
            'error': 'Token inválido o expirado',
            'message': 'El enlace de moderación ha expirado o no es válido. Por favor, accede al panel de administración.'
        }, status=400)

    if token_data.nonce and is_token_consumed(token_data.nonce):
        return render(request, 'moderation_result.html', {
            'success': False,
            'error': 'Token ya utilizado',
            'message': 'Este enlace de moderación ya ha sido utilizado anteriormente.'
        }, status=400)

    user = get_object_or_404(User, id=token_data.item_id)
    tenant = None
    if token_data.tenant_id:
        tenant = Organization.objects.filter(id=token_data.tenant_id, is_active=True).first()

    if not can_moderate(request.user, 'user', user, tenant):
        return render(request, 'moderation_result.html', {
            'success': False,
            'error': 'Permiso denegado',
            'message': 'No tienes permisos suficientes para moderar este usuario en esta organización.'
        }, status=403)

    action = token_data.action
    if action not in ['approve', 'reject']:
        return HttpResponseBadRequest("Acción inválida")

    from ilovevoley.users.models import Membership

    # Verificar si ya fue moderado
    if action == 'approve':
        if tenant:
            membership = Membership.objects.filter(user=user, organization=tenant).first()
            if membership and membership.is_approved:
                return render(request, 'moderation_result.html', {
                    'success': True,
                    'already_moderated': True,
                    'message': f'La membresía de {user.username} en {tenant.name} ya fue aprobada anteriormente.',
                    'item_type': 'usuario',
                    'user': user
                })
        elif user.is_approved:
            return render(request, 'moderation_result.html', {
                'success': True,
                'already_moderated': True,
                'message': f'El usuario {user.username} ya fue aprobado anteriormente.',
                'item_type': 'usuario',
                'user': user
            })

    # GET: Mostrar exclusivamente pantalla de confirmación
    if request.method == 'GET':
        return render(request, 'moderation_confirm.html', {
            'item_type': 'usuario',
            'action': action,
            'target_user': user,
            'tenant': tenant,
            'token': token,
        })

    # POST: Ejecutar mutación consumiendo el token
    if not mark_token_consumed(token_data.nonce):
        return render(request, 'moderation_result.html', {
            'success': False,
            'error': 'Token ya utilizado',
            'message': 'Este enlace de moderación ya ha sido utilizado anteriormente.'
        }, status=400)

    if action == 'approve':
        approve_user_membership(user, tenant=tenant)

        # Enviar email de aprobación al usuario
        if user.email:
            site_url = build_absolute_url('/', tenant=tenant, request=request)
            context = {
                'user': user,
                'site_name': tenant.name if tenant else 'I Love Voley',
                'site_url': site_url,
            }
            send_notification_email(
                subject='Tu cuenta ha sido aprobada en I Love Voley',
                template_name='emails/user_approved.html',
                context=context,
                recipient_list=[user.email]
            )

        org_msg = f" en {tenant.name}" if tenant else ""
        return render(request, 'moderation_result.html', {
            'success': True,
            'action': 'aprobado',
            'message': f'El usuario {user.username} ha sido aprobado correctamente{org_msg} y se le ha enviado un email de notificación.',
            'item_type': 'usuario',
            'user': user
        })

    elif action == 'reject':
        if tenant:
            reject_user_membership(user, tenant)
        else:
            user.is_active = False
            user.save(update_fields=['is_active'])

        if user.email:
            context = {
                'user': user,
                'site_name': tenant.name if tenant else 'I Love Voley',
            }
            send_notification_email(
                subject='Actualización de tu solicitud en I Love Voley',
                template_name='emails/user_rejected.html',
                context=context,
                recipient_list=[user.email]
            )

        org_msg = f" en {tenant.name}" if tenant else ""
        return render(request, 'moderation_result.html', {
            'success': True,
            'action': 'rechazado',
            'message': f'La solicitud de {user.username}{org_msg} ha sido rechazada y se le ha notificado por email.',
            'item_type': 'usuario',
            'user': user
        })


@login_required
def moderate_image(request, token):
    """
    Vista para aprobar/rechazar imagen mediante token seguro.
    GET muestra formulario de confirmación con CSRF.
    POST ejecuta la acción y consume el token.
    """
    if request.method not in ['GET', 'POST']:
        return HttpResponseNotAllowed(['GET', 'POST'])

    token_data = verify_moderation_token(token, check_consumed=False)
    if not token_data or token_data.item_type != 'image':
        return render(request, 'moderation_result.html', {
            'success': False,
            'error': 'Token inválido o expirado',
            'message': 'El enlace de moderación ha expirado o no es válido. Por favor, accede al panel de administración.'
        }, status=400)

    if token_data.nonce and is_token_consumed(token_data.nonce):
        return render(request, 'moderation_result.html', {
            'success': False,
            'error': 'Token ya utilizado',
            'message': 'Este enlace de moderación ya ha sido utilizado anteriormente.'
        }, status=400)

    image = get_object_or_404(Image, id=token_data.item_id)
    tenant = image.organization or (
        Organization.objects.filter(id=token_data.tenant_id, is_active=True).first()
        if token_data.tenant_id else None
    )

    if not can_moderate(request.user, 'image', image, tenant):
        return render(request, 'moderation_result.html', {
            'success': False,
            'error': 'Permiso denegado',
            'message': 'No tienes permisos suficientes para moderar esta imagen.'
        }, status=403)

    image_data_uri = image_to_data_uri(image.image)

    action = token_data.action
    if action not in ['approve', 'reject']:
        return HttpResponseBadRequest("Acción inválida")

    if image.status != 'pending':
        status_text = 'aprobada' if image.status == 'approved' else 'rechazada'
        return render(request, 'moderation_result.html', {
            'success': True,
            'already_moderated': True,
            'message': f'La imagen "{image.title}" ya fue {status_text} anteriormente.',
            'item_type': 'imagen',
            'image': image,
            'image_data_uri': image_data_uri,
        })

    # GET: Pantalla de confirmación
    if request.method == 'GET':
        return render(request, 'moderation_confirm.html', {
            'item_type': 'imagen',
            'action': action,
            'target_image': image,
            'image_data_uri': image_data_uri,
            'tenant': tenant,
            'token': token,
        })

    # POST: Ejecutar acción consumiendo el token
    if not mark_token_consumed(token_data.nonce):
        return render(request, 'moderation_result.html', {
            'success': False,
            'error': 'Token ya utilizado',
            'message': 'Este enlace de moderación ya ha sido utilizado anteriormente.'
        }, status=400)

    notes = request.POST.get('notes', '').strip()
    if action == 'approve':
        default_notes = 'Aprobada mediante confirmación de email'
        image.moderate(
            moderator=request.user,
            approved=True,
            notes=notes or default_notes
        )

        if image.uploaded_by.email:
            context = {
                'image': image,
                'user': image.uploaded_by,
                'site_name': tenant.name if tenant else 'I Love Voley',
                'is_approved': True,
                'moderation_notes': image.moderation_notes,
            }
            send_notification_email(
                subject=f'Tu imagen "{image.title}" ha sido aprobada',
                template_name='emails/image_approved.html',
                context=context,
                recipient_list=[image.uploaded_by.email]
            )

        return render(request, 'moderation_result.html', {
            'success': True,
            'action': 'aprobada',
            'message': f'La imagen "{image.title}" ha sido aprobada correctamente y el usuario ha sido notificado.',
            'item_type': 'imagen',
            'image': image,
            'image_data_uri': image_data_uri,
        })

    elif action == 'reject':
        default_notes = 'Rechazada mediante confirmación de email'
        image.moderate(
            moderator=request.user,
            approved=False,
            notes=notes or default_notes
        )

        if image.uploaded_by.email:
            context = {
                'image': image,
                'user': image.uploaded_by,
                'site_name': tenant.name if tenant else 'I Love Voley',
                'is_approved': False,
                'moderation_notes': image.moderation_notes,
            }
            send_notification_email(
                subject=f'Tu imagen "{image.title}" ha sido rechazada',
                template_name='emails/image_rejected.html',
                context=context,
                recipient_list=[image.uploaded_by.email]
            )

        return render(request, 'moderation_result.html', {
            'success': True,
            'action': 'rechazada',
            'message': f'La imagen "{image.title}" ha sido rechazada y el usuario ha sido notificado.',
            'item_type': 'imagen',
            'image': image,
            'image_data_uri': image_data_uri,
        })
