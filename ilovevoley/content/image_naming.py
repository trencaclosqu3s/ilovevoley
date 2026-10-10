"""Lógica centralizada para nombrado descriptivo de imágenes y rutas en storage.

Formatea títulos visibles y nombres de fichero limpios según el contexto:
- Partidos: Local vs Visitante - DD/MM/YYYY - NNN
- Álbumes: Nombre del Álbum - NNN
- Fotos sueltas: Título descriptivo (- NNN)
"""
import os
import re
import uuid
from datetime import date, datetime

from django.core.files.storage import default_storage
from django.utils import timezone
from django.utils.text import slugify


def sanitize_slug(text, max_length=50):
    """Genera un slug limpio y seguro para nombres de fichero en storage."""
    raw = (text or '').replace("'", "-").replace("’", "-")
    slug = slugify(raw)
    if not slug:
        return 'foto'
    return slug[:max_length].rstrip('-')


def format_sequence(seq):
    """Devuelve el secuencial con padding de al menos 3 dígitos."""
    return f"{int(seq):03d}"


def build_descriptive_title(*, match=None, album_name='', base_title='', seq=None):
    """Construye un título legible para la UI."""
    seq_str = format_sequence(seq) if seq is not None else ''

    if match is not None:
        home = getattr(match, 'home_team_display', None) or (match.home_team.name if match.home_team else 'Local')
        away = getattr(match, 'away_team_display', None) or (match.away_team.name if match.away_team else 'Visitante')
        if match.match_date:
            if isinstance(match.match_date, datetime) and timezone.is_aware(match.match_date):
                local_dt = timezone.localtime(match.match_date)
            else:
                local_dt = match.match_date
            match_date_str = local_dt.strftime('%d/%m/%Y')
        else:
            match_date_str = timezone.now().strftime('%d/%m/%Y')
        if seq_str:
            return f"{home} vs {away} - {match_date_str} - {seq_str}"
        return f"{home} vs {away} - {match_date_str}"

    if album_name:
        name = album_name.strip()
        if seq_str:
            return f"{name} - {seq_str}"
        return name

    if base_title:
        title = base_title.strip()
        if seq_str:
            return f"{title} - {seq_str}"
        return title

    return ''


def get_next_sequence_number(*, match=None, album_group_id=None, base_title='', organization=None, exclude_image_id=None):
    """Calcula el siguiente número de secuencia disponible en base de datos."""
    from ilovevoley.content.models import Image

    qs = Image.objects.all()
    if organization is not None:
        qs = qs.filter(organization=organization)
    if exclude_image_id:
        qs = qs.exclude(pk=exclude_image_id)

    if match is not None:
        return qs.filter(match=match).count() + 1
    if album_group_id:
        return qs.filter(album_group_id=album_group_id).count() + 1
    if base_title:
        return qs.filter(title__istartswith=base_title).count() + 1

    return 1


def build_descriptive_storage_path(*, match=None, album_name='', base_title='', seq=1, extension='jpg', storage=None, now_date=None):
    """Construye la ruta en storage para la imagen, evitando colisiones en disco."""
    if storage is None:
        storage = default_storage
    if now_date is None:
        now = timezone.now()
        year = now.year
        month = now.month
    else:
        year = now_date.year
        month = now_date.month

    # Normalizar extensión
    ext = extension.lstrip('.').lower()
    if not ext or ext in ['heic', 'heif']:
        ext = 'jpg'

    base_dir = f"images/{year}/{month:02d}"

    if match is not None:
        home = getattr(match, 'home_team_display', None) or (match.home_team.name if match.home_team else 'local')
        away = getattr(match, 'away_team_display', None) or (match.away_team.name if match.away_team else 'visitante')
        home_slug = sanitize_slug(home, max_length=30)
        away_slug = sanitize_slug(away, max_length=30)
        if match.match_date:
            if isinstance(match.match_date, datetime) and timezone.is_aware(match.match_date):
                local_dt = timezone.localtime(match.match_date)
            else:
                local_dt = match.match_date
            date_str = local_dt.strftime('%Y-%m-%d')
        else:
            date_str = f"{year}-{month:02d}-01"
        prefix = f"{home_slug}-vs-{away_slug}-{date_str}"
    elif album_name:
        prefix = sanitize_slug(album_name, max_length=50)
    elif base_title:
        prefix = sanitize_slug(base_title, max_length=50)
    else:
        prefix = "foto"

    curr_seq = int(seq) if seq else 1
    while True:
        candidate_filename = f"{prefix}-{format_sequence(curr_seq)}.{ext}"
        candidate_path = f"{base_dir}/{candidate_filename}"
        if not storage.exists(candidate_path):
            return candidate_path
        curr_seq += 1


def is_generic_camera_filename(name):
    """Detecta si un nombre es genérico de cámara, móvil o UUID."""
    if not name or not name.strip():
        return True
    cleaned = name.strip()
    try:
        uuid.UUID(cleaned)
        return True
    except (ValueError, AttributeError):
        pass
    import re
    if re.match(r'^(IMG|DSC|DSCN|SAM|P|WP|PIC|PICT|DCIM|IMAGE|PHOTO)[_-]?\d+$', cleaned, re.IGNORECASE):
        return True
    return False


def get_image_upload_path(instance, filename):
    """Punto de entrada para el atributo upload_to del ImageField de Image."""
    from ilovevoley.videos.utils import build_uuid_upload_path

    if instance is None:
        now = timezone.now()
        return build_uuid_upload_path(f'images/{now.year}/{now.month:02d}', filename)

    _, ext = os.path.splitext(filename)

    match = getattr(instance, 'match', None)
    album_name = getattr(instance, 'album_name', '')
    album_group_id = getattr(instance, 'album_group_id', None)
    title = getattr(instance, 'title', '')

    is_generic_title = is_generic_camera_filename(title)

    if not match and not album_name and not album_group_id and is_generic_title:
        now = timezone.now()
        return build_uuid_upload_path(f'images/{now.year}/{now.month:02d}', filename)

    # Si el título ya contiene un secuencial al final (ej. " - 003"), usarlo como base
    seq = None
    clean_title = title
    if title:
        match_seq = re.search(r'^(.*?)\s*-\s*(\d{3,})$', title)
        if match_seq:
            clean_title = match_seq.group(1).strip()
            seq = int(match_seq.group(2))

    if seq is None:
        seq = get_next_sequence_number(
            match=match,
            album_group_id=album_group_id,
            base_title='' if is_generic_title else clean_title,
            organization=getattr(instance, 'organization', None),
            exclude_image_id=instance.pk,
        )

    # Determinar fecha de subida (o del partido)
    upload_date = getattr(instance, 'upload_date', None) or timezone.now()
    if hasattr(upload_date, 'date'):
        now_date = upload_date.date()
    else:
        now_date = upload_date

    storage = instance.image.storage if hasattr(instance, 'image') and instance.image else default_storage

    return build_descriptive_storage_path(
        match=match,
        album_name=album_name,
        base_title='' if is_generic_title else clean_title,
        seq=seq,
        extension=ext,
        storage=storage,
        now_date=now_date,
    )
