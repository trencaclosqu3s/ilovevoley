import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import Image, League, ScrapingEndpoint
from ilovevoley.core.email_utils import enqueue_on_commit
from ilovevoley.core.tasks import notify_image_pending_task

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Image)
def image_uploaded_handler(sender, instance, created, **kwargs):
    """
    Maneja cuando se sube una nueva imagen (pendiente de moderación).
    El SMTP se encola en Celery tras el commit (issue #114).
    """
    if not (created and instance.status == 'pending'):
        return
    if getattr(instance, '_skip_pending_email', False):
        return
    if not settings.EMAIL_NOTIFICATIONS.get('image_pending', True):
        return

    enqueue_on_commit(notify_image_pending_task, instance.id)


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

    if created_count > 0:
        logger.info(
            "Configurados %d endpoints de scraping para la liga '%s' (id=%s)",
            created_count,
            instance.name,
            instance.pk,
        )
