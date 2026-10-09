import hashlib
import io
import logging
import re
from typing import Optional, Tuple
from urllib.parse import urljoin

from django.core.files.base import ContentFile
from PIL import Image, ImageOps
import pypdf
import requests

from ilovevoley.competitions.models import Match, MatchActaPhoto

logger = logging.getLogger(__name__)

# Matches pdf.asp?o=<número>.<ext> with pure digits in <número>, rejecting <número>_<número>.pdf
PHOTO_URL_PATTERN = re.compile(r'pdf\.asp\?o=(\d+)\.([a-zA-Z]+)$', re.IGNORECASE)

DEFAULT_USER_AGENT = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)

MAX_IMAGE_DIMENSION = 1600


def is_tenant_match(match: Match, organizations=None) -> bool:
    """Comprueba si el partido pertenece a algún tenant activo.

    ``organizations`` permite reutilizar la lista de organizaciones activas entre llamadas.
    """
    from ilovevoley.core.models import Organization

    if organizations is None:
        organizations = Organization.objects.filter(is_active=True)
    return any(
        Match.all_objects.filter(pk=match.pk).for_tenant(org).exists()
        for org in organizations
    )


def extract_image_from_pdf(pdf_bytes: bytes) -> Tuple[Optional[bytes], str]:
    """
    Extrae la imagen del acta desde los bytes de un PDF, la deduplica y la normaliza.

    Devuelve (jpeg_bytes, status) con status en:
    - 'ok': imagen extraída y normalizada a JPEG limpio (~1600px, RGB, sin EXIF)
    - 'expired': no es PDF (p. ej. texto «El acta no se ha guardado en el servidor»)
    - 'unreadable': PDF sin imágenes utilizables o corrupto
    """
    if not pdf_bytes or not pdf_bytes.startswith(b'%PDF'):
        return None, 'expired'

    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    except Exception as e:
        logger.warning(f'Error leyendo estructura PDF del acta: {e}')
        return None, 'unreadable'

    seen_hashes = set()
    extracted_images = []

    for page in reader.pages:
        try:
            page_images = page.images
        except Exception as e:
            logger.warning(f'Error accediendo a imágenes de página: {e}')
            continue

        for img in page_images:
            try:
                data = img.data
                img_hash = hashlib.sha256(data).hexdigest()
                if img_hash in seen_hashes:
                    continue
                seen_hashes.add(img_hash)
                extracted_images.append(img.image)
            except Exception as e:
                logger.warning(f'Error procesando imagen individual de PDF: {e}')
                continue

    if not extracted_images:
        return None, 'unreadable'

    # Ordenar por área descendente para priorizar la imagen principal sobre posibles máscaras
    extracted_images.sort(key=lambda im: im.size[0] * im.size[1], reverse=True)
    pil_img = extracted_images[0]

    # Descartar imágenes vacías o de tamaño insignificante
    if pil_img.size[0] <= 10 or pil_img.size[1] <= 10:
        return None, 'unreadable'

    try:
        pil_img = ImageOps.exif_transpose(pil_img)
    except Exception:
        pass

    # Convertir a RGB (aplanando canal alfa sobre blanco si existe)
    if pil_img.mode != 'RGB':
        if pil_img.mode in ('RGBA', 'LA') or ('transparency' in pil_img.info):
            rgba = pil_img.convert('RGBA')
            bg = Image.new('RGB', rgba.size, (255, 255, 255))
            bg.paste(rgba, mask=rgba.split()[3])
            pil_img = bg
        else:
            pil_img = pil_img.convert('RGB')

    # Redimensionar si el lado largo supera MAX_IMAGE_DIMENSION (sin ampliar imágenes menores)
    w, h = pil_img.size
    longest = max(w, h)
    if longest > MAX_IMAGE_DIMENSION:
        scale = MAX_IMAGE_DIMENSION / float(longest)
        new_w = int(round(w * scale))
        new_h = int(round(h * scale))
        pil_img = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    out_io = io.BytesIO()
    # Guardar JPEG limpio sin metadatos EXIF ni GPS
    pil_img.save(out_io, format='JPEG', quality=85, optimize=True)
    return out_io.getvalue(), 'ok'


def fetch_acta_image(source_url: str, timeout: int = 30) -> Tuple[Optional[bytes], str]:
    """
    Descarga el PDF de la URL dada y extrae la imagen del acta normalizada.

    Devuelve (jpeg_bytes, status) con status en ('ok', 'expired', 'unreadable', 'error').
    'error' es un fallo transitorio de red o del servidor federativo: la foto se reintenta.
    """
    headers = {
        'User-Agent': DEFAULT_USER_AGENT,
        'Accept': 'application/pdf,*/*',
    }
    try:
        response = requests.get(
            source_url,
            headers=headers,
            allow_redirects=True,
            timeout=timeout,
        )
    except requests.RequestException as e:
        logger.warning(f'Error descargando acta desde {source_url}: {e}')
        return None, 'error'

    if response.status_code >= 500:
        logger.warning(f'Error {response.status_code} del servidor federativo descargando {source_url}')
        return None, 'error'
    if response.status_code >= 400:
        return None, 'expired'

    return extract_image_from_pdf(response.content)


def download_and_prepare_acta_photo(photo: MatchActaPhoto) -> bool:
    """
    Descarga y prepara la imagen del acta para un registro MatchActaPhoto.

    Actualiza el estado a 'expired' o 'unreadable' si la descarga o extracción falla;
    un fallo transitorio de red o 5xx no cambia el estado.
    Si tiene éxito, guarda la imagen normalizada en photo.image.
    """
    if photo.status in ('approved', 'rejected'):
        return False

    jpeg_bytes, status = fetch_acta_image(photo.source_url)
    if status == 'error':
        # Transitorio: se queda en pending_download para el siguiente ciclo
        return False

    if status == 'expired':
        photo.status = 'expired'
        photo.save(update_fields=['status', 'updated_at'])
        return False

    if status == 'unreadable' or not jpeg_bytes:
        photo.status = 'unreadable'
        photo.save(update_fields=['status', 'updated_at'])
        return False

    # Guardar imagen limpia en photo.image
    filename = f"acta_{photo.match.federation_id or photo.match_id}.jpg"
    photo.image.save(filename, ContentFile(jpeg_bytes), save=False)
    photo.status = 'downloaded'
    photo.save(update_fields=['image', 'status', 'updated_at'])
    return True


def process_acta_photos_from_html(
    html: str,
    league: Optional[object] = None,
    round_number: Optional[int] = None,
) -> int:
    """
    Busca enlaces a fotos de acta manual en el HTML de resultados.

    Crea MatchActaPhoto para partidos de un tenant que no tienen acta HTML
    y cuyo enlace a foto es del tipo pdf.asp?o=<número>.<ext>.
    Es idempotente: no pisa estados terminados (approved, rejected).
    """
    if not html:
        return 0

    from ilovevoley.core.models import Organization

    organizations = list(Organization.objects.filter(is_active=True))
    created_or_updated = 0
    blocks = html.split("class='info_partido")[1:]

    for block in blocks:
        # Si tiene acta HTML en el bloque, no es un partido solo-foto
        if re.search(r"title=['\"]Ver Acta['\"]", block):
            continue

        # Buscar enlace a «Ver Foto Acta»
        foto_match = re.search(
            r"<a\s+[^>]*title=['\"]Ver Foto Acta['\"][^>]*href=['\"]([^'\"]+)['\"]",
            block,
        ) or re.search(
            r"<a\s+[^>]*href=['\"]([^'\"]+)['\"][^>]*title=['\"]Ver Foto Acta['\"]",
            block,
        )
        if not foto_match:
            continue

        raw_url = foto_match.group(1).strip()
        full_url = urljoin('https://www.voleibolib.net/', raw_url)

        # Solo URLs del tipo pdf.asp?o=<número>.<ext> (NO o=<número>_<número>.pdf)
        url_match = PHOTO_URL_PATTERN.search(full_url)
        if not url_match:
            continue

        fed_match_id = url_match.group(1)

        # Buscar el partido en BD
        match = Match.all_objects.filter(federation_id=fed_match_id).first()
        if not match and league:
            clubs = re.findall(r'clubes/(\d+)mini', block)
            if len(clubs) >= 2 and round_number:
                match = Match.all_objects.filter(
                    league=league,
                    round_number=round_number,
                    federation_club_local_id=clubs[0],
                    federation_club_away_id=clubs[1],
                ).first()

        if not match:
            continue

        # Si el partido ya tiene acta HTML en BD, no procesar foto
        if match.acta_html:
            continue

        # Solo para partidos de un tenant
        if not is_tenant_match(match, organizations):
            continue

        # Idempotencia: no pisar estados aprobados ni rechazados
        photo = MatchActaPhoto.objects.filter(match=match).first()
        if photo:
            if photo.status in ('approved', 'rejected'):
                continue
            if photo.source_url != full_url:
                photo.source_url = full_url
                photo.save(update_fields=['source_url', 'updated_at'])
                created_or_updated += 1
        else:
            MatchActaPhoto.objects.create(
                match=match,
                source_url=full_url,
                status='pending_download',
            )
            created_or_updated += 1

    return created_or_updated
