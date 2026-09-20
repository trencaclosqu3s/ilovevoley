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

    # Las ligas de amistosos se gestionan manualmente, sin scraping automático
    if instance.competition_type == 'friendly':
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