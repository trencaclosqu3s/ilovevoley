"""Tareas Celery de la app content."""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='generate_image_thumbnails_task')
def generate_image_thumbnails_task(image_id):
    """Genera las miniaturas responsivas de una imagen por su id.

    El nombre es explícito porque las filas de PeriodicTask dependen de él.
    """
    from ilovevoley.content.models import Image
    from ilovevoley.content.thumbnails import generate_image_thumbnails

    try:
        image = Image.objects.get(pk=image_id)
    except Image.DoesNotExist:
        logger.warning('Imagen %s no encontrada para generar miniaturas', image_id)
        return {'generated': 0}

    try:
        return {'generated': len(generate_image_thumbnails(image))}
    except Exception:
        # Un original corrupto o un fallo de storage no debe quedar en silencio:
        # la galería cae al original y aquí queda la traza para investigar.
        logger.exception('Fallo generando miniaturas de la imagen %s', image_id)
        return {'generated': 0, 'error': 'thumbnail_generation_failed'}
