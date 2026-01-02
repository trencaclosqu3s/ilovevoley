from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings
from .models import Image, Match, League, ScrapingEndpoint
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
                'site_name': 'I Love Voley',
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
                    'site_name': 'I Love Voley',
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


# Calendar sync signals for Match model
@receiver(post_save, sender=Match)
def match_saved_handler(sender, instance, created, **kwargs):
    """
    Trigger calendar sync when a match is created or updated.
    """
    if not settings.GOOGLE_CALENDAR_ENABLED:
        return
    
    # Only sync if the match has categories (required for filtering users)
    if not instance.league or not instance.league.categories.exists():
        return
    
    from videosvoley.core.tasks.calendar_tasks import sync_match_for_users
    
    if created:
        # New match - sync for all users who have this category
        sync_match_for_users.apply_async(args=[instance.id], countdown=10)
        print(f"New match {instance.id} created, queuing calendar sync for users")
    else:
        # Updated match - check if important fields changed
        if hasattr(instance, '_old_match_date') or hasattr(instance, '_old_venue') or hasattr(instance, '_old_status'):
            sync_match_for_users.apply_async(args=[instance.id], countdown=5)
            print(f"Match {instance.id} updated, queuing calendar sync for users")


@receiver(post_delete, sender=Match)
def match_deleted_handler(sender, instance, **kwargs):
    """
    Handle match deletion - this would require deleting calendar events.
    For now, we'll just log it since the calendar events will remain orphaned.
    """
    if not settings.GOOGLE_CALENDAR_ENABLED:
        return
        
    # TODO: Implement calendar event deletion for deleted matches
    # This would require storing event IDs in a separate model or
    # searching for events by match metadata
    print(f"Match {instance.id} deleted - calendar events may need manual cleanup")


# Add tracking for match changes
@receiver(post_save, sender=Match)
def track_match_changes(sender, instance, **kwargs):
    """
    Track changes in match fields that affect calendar events
    """
    # Clean up any tracking attributes
    for attr in ['_old_match_date', '_old_venue', '_old_status']:
        if hasattr(instance, attr):
            delattr(instance, attr)


# =============================================================================
# League signals - Auto-crear endpoints de scraping
# =============================================================================

@receiver(post_save, sender=League)
def create_default_scraping_endpoints(sender, instance, created, **kwargs):
    """
    Crea automáticamente los 3 endpoints básicos de scraping cuando se crea una liga.
    Esto asegura que las ligas creadas desde el admin tengan la misma configuración
    que las creadas con el comando setup_league.
    """
    if not created:
        # Solo crear endpoints para ligas nuevas
        return
    
    # Configuración de endpoints por defecto (igual que en setup_league.py)
    endpoints_config = [
        {
            'endpoint_type': 'standings',
            'url_pattern': 'JSON/get_clasificacion.asp?id={league_id}',
            'parser_type': 'table_standings'
        },
        {
            'endpoint_type': 'results',
            'url_pattern': 'JSON/get_resultados.asp?id={league_id}&jor={round}',
            'parser_type': 'match_results'
        },
        {
            'endpoint_type': 'calendar',
            'url_pattern': 'JSON/get_calendario.asp?id={league_id}',
            'parser_type': 'match_calendar'
        }
    ]
    
    created_count = 0
    for endpoint_config in endpoints_config:
        endpoint, endpoint_created = ScrapingEndpoint.objects.get_or_create(
            league=instance,
            endpoint_type=endpoint_config['endpoint_type'],
            defaults={
                'url_pattern': endpoint_config['url_pattern'],
                'parser_type': endpoint_config['parser_type'],
                'is_active': True
            }
        )
        
        if endpoint_created:
            created_count += 1
            print(f"✓ Endpoint creado automáticamente: {endpoint.get_endpoint_type_display()} para {instance.name}")
    
    if created_count > 0:
        print(f"✓ Liga '{instance.name}' configurada con {created_count} endpoints de scraping")
    else:
        print(f"ℹ Liga '{instance.name}' ya tenía endpoints configurados")