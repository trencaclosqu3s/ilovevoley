"""Procesamiento seguro de imágenes enviadas por el cliente como data-URI."""
import base64
import uuid
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image

ALLOWED_IMAGE_MIME_TYPES = {
    'image/jpeg': 'JPEG',
    'image/jpg': 'JPEG',
    'image/png': 'PNG',
    'image/webp': 'WEBP',
}

MAX_IMAGE_UPLOAD_SIZE = 5 * 1024 * 1024


class InvalidImageError(ValueError):
    """El data-URI recibido no contiene una imagen permitida."""


def decode_cropped_image(data_uri, *, max_size=MAX_IMAGE_UPLOAD_SIZE, filename=None):
    """
    Convierte un data-URI de imagen recortada en un ContentFile JPEG seguro.

    Valida la cabecera MIME, el tamaño del payload y que el contenido sea una
    imagen real según Pillow. Re-codifica siempre a JPEG para descartar cargas
    arbitrarias (p.ej. HTML con extensión falsificada) y fuerza nombre .jpg.
    """
    if not isinstance(data_uri, str) or not data_uri.startswith('data:'):
        raise InvalidImageError('Formato de imagen no válido.')

    header, _, payload = data_uri.partition(';base64,')
    if not payload:
        raise InvalidImageError('Formato de imagen no válido.')

    mime_type = header[len('data:'):].strip().lower()
    expected_format = ALLOWED_IMAGE_MIME_TYPES.get(mime_type)
    if expected_format is None:
        raise InvalidImageError('Formato no permitido. Use JPG, PNG o WebP.')

    try:
        raw = base64.b64decode(payload, validate=True)
    except ValueError:
        raise InvalidImageError('La imagen no se pudo decodificar.') from None

    if len(raw) > max_size:
        max_mb = max_size // (1024 * 1024)
        raise InvalidImageError(
            f'El archivo es demasiado grande. Tamaño máximo: {max_mb}MB.'
        )

    try:
        with Image.open(BytesIO(raw)) as image:
            image.verify()
        with Image.open(BytesIO(raw)) as image:
            if image.format != expected_format:
                raise InvalidImageError(
                    'El contenido no coincide con el formato declarado.'
                )
            if image.mode != 'RGB':
                image = image.convert('RGB')
            output = BytesIO()
            image.save(output, format='JPEG', quality=90, optimize=True)
    except InvalidImageError:
        raise
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise InvalidImageError('El archivo no es una imagen válida.') from None

    output.seek(0)
    return ContentFile(output.read(), name=filename or f'{uuid.uuid4().hex}.jpg')
