"""Derivación de miniaturas responsivas (WebP/AVIF) a partir de las imágenes.

Cada imagen original se reduce a dos anchos (400px para las rejillas y 1600px
para el visor), en WebP y, si la build de Pillow lo soporta, también en AVIF.
Los ficheros se guardan junto al original en el storage por defecto y su nombre
se persiste en los campos ``thumbnail_*`` del modelo ``Image``.
"""
import logging
import os
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)

THUMBNAIL_VARIANTS = (
    ('thumbnail_small', 400, 'webp'),
    ('thumbnail_large', 1600, 'webp'),
    ('thumbnail_small_avif', 400, 'avif'),
    ('thumbnail_large_avif', 1600, 'avif'),
)

WEBP_QUALITY = 82
AVIF_QUALITY = 55
AVIF_SPEED = 6


def _supports_format(fmt):
    """Comprueba si la build de Pillow puede codificar el formato dado."""
    try:
        from PIL import features
    except ImportError:
        return False
    return features.check(fmt)


def _prepare(img):
    """Normaliza el modo de color y aplica la orientación EXIF."""
    from PIL import Image as PILImage

    if img.mode in ('CMYK', 'YCbCr', 'LAB', 'HSV'):
        img = img.convert('RGB')
    elif img.mode == 'P':
        img = img.convert('RGBA' if 'transparency' in img.info else 'RGB')
    return img


def _encode_variant(base, width, fmt):
    """Redimensiona (solo si procede) y codifica una variante en memoria."""
    from PIL import Image as PILImage

    img = _prepare(base)
    if img.width > width:
        ratio = width / img.width
        img = img.resize((width, max(1, round(img.height * ratio))), PILImage.Resampling.LANCZOS)

    buffer = BytesIO()
    try:
        if fmt == 'webp':
            img.save(buffer, format='WEBP', quality=WEBP_QUALITY, method=6)
        else:
            try:
                img.save(buffer, format='AVIF', quality=AVIF_QUALITY, speed=AVIF_SPEED)
            except TypeError:
                img.save(buffer, format='AVIF', quality=AVIF_QUALITY)
    except Exception as exc:
        logger.warning('No se pudo generar la miniatura %spx %s: %s', width, fmt, exc)
        return None
    return buffer.getvalue()


def _variant_name(original_name, width, fmt):
    base, _ = os.path.splitext(original_name)
    return f'{base}_{width}.{fmt}'


def generate_image_thumbnails(image):
    """Genera y persiste las miniaturas de ``image``.

    Devuelve un dict ``{nombre_de_campo: nombre_en_storage}`` con las variantes
    creadas. Es idempotente: vuelve a escribir sobre los mismos ficheros.
    """
    if not image.image:
        return {}

    try:
        from PIL import Image as PILImage, ImageOps
    except ImportError:
        logger.warning('Pillow no está instalado; no se generan miniaturas')
        return {}

    generated = {}
    storage = image.image.storage
    image.image.open('rb')
    try:
        with PILImage.open(image.image) as opened:
            base = ImageOps.exif_transpose(opened)
            base.load()
            for field_name, width, fmt in THUMBNAIL_VARIANTS:
                if not _supports_format(fmt):
                    continue
                data = _encode_variant(base, width, fmt)
                if data is None:
                    continue
                name = _variant_name(image.image.name, width, fmt)
                if storage.exists(name):
                    storage.delete(name)
                saved_name = storage.save(name, ContentFile(data))
                setattr(image, field_name, saved_name)
                generated[field_name] = saved_name
    finally:
        image.image.close()

    if generated:
        image.save(update_fields=list(generated.keys()))
    return generated


def schedule_thumbnail_generation(image):
    """Genera las miniaturas de forma síncrona o delegando en Celery.

    En producción se encola la tarea para no bloquear la subida; si el broker
    no está disponible se cae a generación en línea.
    """
    if not getattr(settings, 'THUMBNAIL_GENERATION_ASYNC', False):
        return generate_image_thumbnails(image)

    try:
        from ilovevoley.content.tasks import generate_image_thumbnails_task
        generate_image_thumbnails_task.delay(image.pk)
    except Exception as exc:
        logger.warning('No se pudo encolar la generación de miniaturas (%s); se genera en línea', exc)
        return generate_image_thumbnails(image)
    return None
