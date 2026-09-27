"""Generación temporal de ZIPs de álbumes de imágenes (#127)."""
import logging
import shutil
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.urls import reverse

logger = logging.getLogger(__name__)

ALBUM_ZIP_SALT = 'ilovevoley.album_zip.v1'
JOB_CACHE_PREFIX = 'album_zip:job:'
REL_DIR = 'tmp/album_zips'


def album_zip_max_age():
    return int(getattr(settings, 'ALBUM_ZIP_LINK_MAX_AGE', 24 * 3600))


def _job_key(job_id):
    return f'{JOB_CACHE_PREFIX}{job_id}'


def media_zip_dir():
    return Path(settings.MEDIA_ROOT) / REL_DIR


def job_dest_path(job_id):
    return media_zip_dir() / f'{job_id}.zip'


def set_job_state(job_id, **data):
    payload = cache.get(_job_key(job_id)) or {}
    payload.update(data)
    cache.set(_job_key(job_id), payload, timeout=album_zip_max_age())
    return payload


def get_job_state(job_id):
    return cache.get(_job_key(job_id))


def create_pending_job(*, organization_id, user_id, scope, scope_id, filename):
    job_id = str(uuid.uuid4())
    set_job_state(
        job_id,
        status='pending',
        organization_id=organization_id,
        user_id=user_id,
        scope=scope,
        scope_id=str(scope_id),
        filename=filename,
    )
    return job_id


def build_album_zip_file(*, queryset, dest_path):
    """Escribe un ZIP en disco leyendo cada imagen en streaming.

    No carga el álbum completo en memoria: copia chunk a chunk desde storage.
    """
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(dest_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for image in queryset.iterator():
            if not image.image:
                continue
            arcname = f'{image.pk}_{Path(image.image.name).name}'
            with zf.open(arcname, 'w') as dest, image.image.open('rb') as src:
                shutil.copyfileobj(src, dest, length=64 * 1024)
            count += 1
    return count


def sign_download_token(job_id, rel_path, filename):
    signer = TimestampSigner(salt=ALBUM_ZIP_SALT)
    return signer.sign(f'{job_id}|{rel_path}|{filename}')


def unsign_download_token(token, max_age=None):
    if max_age is None:
        max_age = album_zip_max_age()
    signer = TimestampSigner(salt=ALBUM_ZIP_SALT)
    value = signer.unsign(token, max_age=max_age)
    job_id, rel_path, filename = value.split('|', 2)
    return job_id, rel_path, filename


def build_download_url(job_id, rel_path, filename):
    token = sign_download_token(job_id, rel_path, filename)
    return reverse('content:album_zip_download') + '?' + urlencode({'token': token})


def safe_resolve_media_path(rel_path):
    """Resuelve ruta relativa a MEDIA_ROOT rechazando traversal."""
    if not rel_path or rel_path.startswith('/') or '\\' in rel_path:
        raise ValueError('invalid path')
    base = Path(settings.MEDIA_ROOT).resolve()
    full = (base / rel_path).resolve()
    if base not in full.parents and full != base:
        raise ValueError('path escape')
    return full


def mark_job_ready(job_id, rel_path, filename):
    return set_job_state(
        job_id,
        status='ready',
        path=rel_path,
        filename=filename,
        download_url=build_download_url(job_id, rel_path, filename),
    )


def mark_job_failed(job_id, error):
    logger.warning('album zip job %s failed: %s', job_id, error)
    return set_job_state(job_id, status='failed', error=str(error))


def parse_download_token(token):
    try:
        return unsign_download_token(token)
    except SignatureExpired:
        return None
    except (BadSignature, ValueError):
        return None
