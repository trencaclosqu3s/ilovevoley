from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import Image
from videosvoley.core.email_utils import send_notification_email
from videosvoley.core.moderation_views import generate_moderation_token
import os


@receiver(post_save, sender=Image)
def image_uploaded_handler(sender, instance, created, **kwargs):
    """
    Maneja cuando se sube una nueva imagen (pendiente de moderación)
    """
    if created and instance.status == 'pending':
        print(f"Nueva imagen subida: {instance.title} por {instance.uploaded_by.username}")
        
        # Enviar email de notificación a admins
        if settings.EMAIL_NOTIFICATIONS.get('image_pending', True):
            # Generar tokens de moderación
            approve_token = generate_moderation_token('image', instance.id, 'approve')
            reject_token = generate_moderation_token('image', instance.id, 'reject')
            
            # Preparar imagen para embeber (CID) y adjuntar
            embedded_images = {}
            attachments = []
            if instance.image:
                try:
                    image_path = instance.image.path
                    if os.path.exists(image_path):
                        # Usar CID para embeber la imagen en el HTML
                        embedded_images['pending_image'] = image_path
                        # También adjuntar para que se pueda descargar
                        attachments.append(image_path)
                except Exception as e:
                    print(f"No se pudo procesar la imagen: {str(e)}")
            
            context = {
                'image': instance,
                'user': instance.uploaded_by,
                'site_name': 'VideosVoley',
                'admin_url': f'/admin/videos/image/{instance.id}/change/',
                'image_cid': 'pending_image' if embedded_images else None,  # CID para usar en el template
                'approve_url': f'/moderate/image/{approve_token}/',
                'reject_url': f'/moderate/image/{reject_token}/',
            }
            send_notification_email(
                subject=f'Nueva imagen pendiente de moderación: {instance.title}',
                template_name='emails/image_pending.html',
                context=context,
                attachments=attachments if attachments else None,
                embedded_images=embedded_images if embedded_images else None
            )


@receiver(post_save, sender=Image)
def image_moderated_handler(sender, instance, created, **kwargs):
    """
    Envía email al usuario cuando su imagen es moderada (aprobada o rechazada)
    """
    if not created and instance.moderated_by:
        # Verificar si cambió de pendiente a moderada
        if hasattr(instance, '_old_status') and instance._old_status == 'pending':
            print(f"Imagen moderada: {instance.title} - Estado: {instance.status}")
            
            # Enviar email al usuario que subió la imagen
            if settings.EMAIL_NOTIFICATIONS.get('image_moderated', True) and instance.uploaded_by.email:
                context = {
                    'image': instance,
                    'user': instance.uploaded_by,
                    'site_name': 'VideosVoley',
                    'is_approved': instance.status == 'approved',
                    'moderation_notes': instance.moderation_notes,
                }
                
                if instance.status == 'approved':
                    subject = f'Tu imagen "{instance.title}" ha sido aprobada'
                    template_name = 'emails/image_approved.html'
                else:
                    subject = f'Tu imagen "{instance.title}" ha sido rechazada'
                    template_name = 'emails/image_rejected.html'
                
                send_notification_email(
                    subject=subject,
                    template_name=template_name,
                    context=context,
                    recipient_list=[instance.uploaded_by.email]
                )


# Hook para trackear cambios en status de imagen
@receiver(post_save, sender=Image)
def track_image_status_changes(sender, instance, **kwargs):
    """
    Trackea cambios en el estado de moderación de la imagen
    """
    if hasattr(instance, '_old_status'):
        del instance._old_status