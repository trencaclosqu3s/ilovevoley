"""Servicio y utilidades del timeline multimedia compartible de un partido."""
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.translation import gettext as _

from ilovevoley.core.security import safe_get
from ilovevoley.videos.scraping import parse_acta_lineup

from .models import MatchShareLink

ALLOWED_HOURS = (24, 48, 72, 168)
SET_LABELS_CACHE_TTL = 60 * 60 * 24


def default_hours():
    """Horas por defecto del enlace, tomadas de settings con fallback a 48."""
    hours = getattr(settings, 'MATCH_SHARE_LINK_DEFAULT_HOURS', 48)
    return hours if hours in ALLOWED_HOURS else 48


def max_hours():
    return getattr(settings, 'MATCH_SHARE_LINK_MAX_HOURS', 720)


def create_match_share_link(match, organization, user, hours=None):
    """Crea un enlace activo con caducidad acotada a [1, max_hours()]."""
    try:
        hours = int(hours)
    except (TypeError, ValueError):
        hours = default_hours()
    hours = max(1, min(hours, max_hours()))
    return MatchShareLink.objects.create(
        match=match,
        organization=organization,
        created_by=user,
        expires_at=timezone.now() + timedelta(hours=hours),
    )


def resolve_match_share_link(token):
    """Devuelve el enlace activo para un token, o None si no existe/expiró/revocado."""
    link = (
        MatchShareLink.objects
        .select_related('match', 'match__league', 'match__home_team', 'match__away_team', 'organization')
        .filter(token=token)
        .first()
    )
    if link is None or not link.is_active:
        return None
    return link


def revoke_match_share_link(link):
    link.revoke()


def _set_number_of(item):
    if isinstance(item, dict):
        return item.get('set_number')
    return getattr(item, 'set_number', None)


def group_match_media(videos, images, set_labels=None):
    """Agrupa vídeos e imágenes por set. Sets ascendentes; 'Sin set' al final."""
    set_labels = set_labels or {}
    numbers = sorted({
        _set_number_of(item)
        for item in list(videos) + list(images)
        if _set_number_of(item) is not None
    })
    groups = []
    for number in numbers:
        groups.append(_build_group(number, set_labels, videos, images))
    groups.append(_build_group(None, set_labels, videos, images))
    return groups


def _build_group(number, set_labels, videos, images):
    label = _('Sin set') if number is None else set_labels.get(number, _('Set %(number)s') % {'number': number})
    return {
        'set_number': number,
        'label': label,
        'videos': [v for v in videos if _set_number_of(v) == number],
        'images': [i for i in images if _set_number_of(i) == number],
    }


def _set_labels_from_acta(data):
    return {
        index: ((set_data.get('title') or '').strip() or f'Set {index}')
        for index, set_data in enumerate(data.get('sets') or [], start=1)
    }


def get_match_set_labels(match):
    """Títulos de set del acta oficial (cacheados 24 h). {} si no hay acta o falla.

    Si el JSON del acta ya está persistido en ``Match.acta_data`` se usa tal cual:
    evita una descarga HTTP síncrona por cada visita al timeline público. El HTML
    solo se descarga y parsea como fallback (acta antigua sin ``acta_data``).
    """
    if match.acta_data is not None:
        return _set_labels_from_acta(match.acta_data)
    acta_url = match.official_acta_url or match.acta_html
    if not acta_url:
        return {}
    cache_key = f'match_set_labels:{acta_url}'
    labels = cache.get(cache_key)
    if labels is not None:
        return labels
    try:
        content = safe_get(acta_url, allowed_hosts=settings.ACTA_ALLOWED_HOSTS)
        data = parse_acta_lineup(content)
        labels = _set_labels_from_acta(data)
    except Exception:
        return {}
    cache.set(cache_key, labels, SET_LABELS_CACHE_TTL)
    return labels
