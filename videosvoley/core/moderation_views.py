"""
Vistas para moderación con tokens seguros (sin necesidad de login en admin)
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import get_user_model
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.http import HttpResponseForbidden, HttpResponseBadRequest
from django.conf import settings
from django.utils import timezone
from videosvoley.videos.models import Image
from videosvoley.core.email_utils import send_notification_email

User = get_user_model()

# Token expira en 7 días
TOKEN_MAX_AGE = 60 * 60 * 24 * 7


def generate_moderation_token(item_type, item_id, action):
    """
    Genera un token seguro para moderación
    
    Args:
        item_type: 'user' o 'image'
        item_id: ID del usuario o imagen
        action: 'approve' o 'reject'
    
    Returns:
        str: Token firmado
    """
    signer = TimestampSigner()
    value = f"{item_type}:{item_id}:{action}"
    return signer.sign(value)


def verify_moderation_token(token, max_age=TOKEN_MAX_AGE):
    """
    Verifica un token de moderación
    
    Args:
        token: Token a verificar
        max_age: Edad máxima del token en segundos
    
    Returns:
        tuple: (item_type, item_id, action) o None si es inválido
    """
    try:
        signer = TimestampSigner()
        value = signer.unsign(token, max_age=max_age)
        parts = value.split(':')
        if len(parts) == 3:
            item_type, item_id, action = parts
            return item_type, int(item_id), action
    except (BadSignature, SignatureExpired, ValueError):
        pass
    return None


def moderate_user(request, token):
    """
    Vista para aprobar/rechazar usuario mediante token
    """
    result = verify_moderation_token(token)
    
    if not result:
        return render(request, 'moderation_result.html', {
            'success': False,
            'error': 'Token inválido o expirado',
            'message': 'El enlace de moderación ha expirado o no es válido. Por favor, accede al panel de administración.'
        })
    
    item_type, user_id, action = result
    
    if item_type != 'user':
        return HttpResponseBadRequest("Token inválido para esta acción")
    
    user = get_object_or_404(User, id=user_id)
    
    # Verificar que el usuario aún está pendiente
    if user.is_approved and action == 'approve':
        return render(request, 'moderation_result.html', {
            'success': True,
            'already_moderated': True,
            'message': f'El usuario {user.username} ya fue aprobado anteriormente.',
            'item_type': 'usuario',
            'user': user
        })
    
    if action == 'approve':
        user.is_approved = True
        user.save()
        
        # Enviar email de aprobación al usuario
        if user.email:
            context = {
                'user': user,
                'site_name': 'VideosVoley',
                'site_url': request.build_absolute_uri('/'),
            }
            send_notification_email(
                subject='Tu cuenta ha sido aprobada en VideosVoley',
                template_name='emails/user_approved.html',
                context=context,
                recipient_list=[user.email]
            )
        
        return render(request, 'moderation_result.html', {
            'success': True,
            'action': 'aprobado',
            'message': f'El usuario {user.username} ha sido aprobado correctamente y se le ha enviado un email de notificación.',
            'item_type': 'usuario',
            'user': user
        })
    
    elif action == 'reject':
        # En vez de eliminar, podemos desactivar
        user.is_active = False
        user.save()
        
        return render(request, 'moderation_result.html', {
            'success': True,
            'action': 'rechazado',
            'message': f'El usuario {user.username} ha sido rechazado. Su cuenta ha sido desactivada.',
            'item_type': 'usuario',
            'user': user
        })
    
    return HttpResponseBadRequest("Acción inválida")


def moderate_image(request, token):
    """
    Vista para aprobar/rechazar imagen mediante token
    """
    result = verify_moderation_token(token)
    
    if not result:
        return render(request, 'moderation_result.html', {
            'success': False,
            'error': 'Token inválido o expirado',
            'message': 'El enlace de moderación ha expirado o no es válido. Por favor, accede al panel de administración.'
        })
    
    item_type, image_id, action = result
    
    if item_type != 'image':
        return HttpResponseBadRequest("Token inválido para esta acción")
    
    image = get_object_or_404(Image, id=image_id)
    
    # Verificar que la imagen aún está pendiente
    if image.status != 'pending' and action in ['approve', 'reject']:
        status_text = 'aprobada' if image.status == 'approved' else 'rechazada'
        return render(request, 'moderation_result.html', {
            'success': True,
            'already_moderated': True,
            'message': f'La imagen "{image.title}" ya fue {status_text} anteriormente.',
            'item_type': 'imagen',
            'image': image
        })
    
    # Obtener el moderador (el primer superuser)
    moderator = User.objects.filter(is_superuser=True).first()
    
    if action == 'approve':
        image.status = 'approved'
        image.moderated_by = moderator
        image.moderation_date = timezone.now()
        image.moderation_notes = 'Aprobada mediante email'
        image.save()
        
        # Enviar email al usuario que subió la imagen
        if image.uploaded_by.email:
            context = {
                'image': image,
                'user': image.uploaded_by,
                'site_name': 'VideosVoley',
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
            'image': image
        })
    
    elif action == 'reject':
        image.status = 'rejected'
        image.moderated_by = moderator
        image.moderation_date = timezone.now()
        image.moderation_notes = 'Rechazada mediante email'
        image.save()
        
        # Enviar email al usuario que subió la imagen
        if image.uploaded_by.email:
            context = {
                'image': image,
                'user': image.uploaded_by,
                'site_name': 'VideosVoley',
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
            'image': image
        })
    
    return HttpResponseBadRequest("Acción inválida")

