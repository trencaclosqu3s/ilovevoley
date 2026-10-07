"""Procesamiento seguro de imágenes enviadas por el cliente como data-URI."""
import base64
import uuid
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageChops, ImageDraw

ALLOWED_IMAGE_MIME_TYPES = {
    'image/jpeg': 'JPEG',
    'image/jpg': 'JPEG',
    'image/png': 'PNG',
    'image/webp': 'WEBP',
}

MAX_IMAGE_UPLOAD_SIZE = 5 * 1024 * 1024

CREST_SIZE = 256
CREST_PADDING = 0.14
CREST_WHITE_THRESHOLD = 215


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
        max_mb = round(max_size / (1024 * 1024), 1)
        raise InvalidImageError(
            f'El archivo es demasiado grande. Tamaño máximo: {max_mb:g}MB.'
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


def image_to_data_uri(file_or_field):
    """
    Convierte un archivo o campo ImageField de Django en un string data-URI (base64).
    Retorna None si el archivo no existe o no se puede leer.
    """
    if not file_or_field:
        return None
    try:
        import mimetypes
        file_or_field.open('rb')
        try:
            content = file_or_field.read()
        finally:
            file_or_field.close()
        if not content:
            return None
        name = getattr(file_or_field, 'name', '') or ''
        mime_type = mimetypes.guess_type(name)[0] or 'image/jpeg'
        encoded = base64.b64encode(content).decode('ascii')
        return f"data:{mime_type};base64,{encoded}"
    except Exception:
        return None



def normalize_crest(data):
    """
    Normaliza el escudo de un club a un PNG cuadrado con fondo exterior transparente.

    Los escudos de la federación son JPEG con fondo blanco opaco y proporciones
    y márgenes dispares. Se hace transparente solo el blanco conectado con las
    esquinas (el blanco interior del escudo se conserva), se recorta al
    contenido y se centra con margen para que quepa en un círculo.
    Devuelve ``None`` si los bytes no son una imagen o solo hay fondo.
    """
    try:
        with Image.open(BytesIO(data)) as raw:
            image = raw.convert('RGBA')
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return None

    r, g, b, a = image.split()
    lightest_channel = ImageChops.darker(ImageChops.darker(r, g), b)
    mask = lightest_channel.point(lambda v: 255 if v >= CREST_WHITE_THRESHOLD else 0)
    last = (image.width - 1, image.height - 1)
    for corner in ((0, 0), (last[0], 0), (0, last[1]), last):
        if mask.getpixel(corner) == 255:
            ImageDraw.floodfill(mask, corner, 128)
    alpha = ImageChops.multiply(mask.point(lambda v: 0 if v == 128 else 255), a)

    box = alpha.getbbox()
    if box is None:
        return None
    image.putalpha(alpha)
    image = image.crop(box)

    side = round(max(image.size) / (1 - 2 * CREST_PADDING))
    canvas = Image.new('RGBA', (side, side), (0, 0, 0, 0))
    canvas.paste(image, ((side - image.width) // 2, (side - image.height) // 2))
    canvas.thumbnail((CREST_SIZE, CREST_SIZE), Image.Resampling.LANCZOS)
    output = BytesIO()
    canvas.save(output, format='PNG', optimize=True)
    return output.getvalue()
