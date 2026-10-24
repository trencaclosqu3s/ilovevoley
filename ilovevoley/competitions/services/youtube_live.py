"""Resolución del directo público de YouTube (@canal/live -> watch?v=<id>)."""

import logging
import re

from ilovevoley.core.security import safe_get

logger = logging.getLogger(__name__)

LIVE_CHANNEL_RE = re.compile(
    r'^https://(www\.)?youtube\.com/@([A-Za-z0-9._-]+)/live/?$'
)
WATCH_URL_RE = re.compile(
    r'^https://(www\.)?youtube\.com/watch\?v=([A-Za-z0-9_-]{11})$'
)
_LINK_TAG_RE = re.compile(r'<link\b[^>]*>', re.IGNORECASE)
_REL_CANONICAL_RE = re.compile(r'\brel=["\']canonical["\']', re.IGNORECASE)
_HREF_RE = re.compile(r'\bhref=["\']([^"\']+)["\']', re.IGNORECASE)

_USER_AGENT = (
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
)


def is_live_channel_url(url) -> bool:
    """True si la URL es https://(www.)youtube.com/@handle/live."""
    if not isinstance(url, str):
        return False
    return bool(LIVE_CHANNEL_RE.match(url))


def is_watch_url(url) -> bool:
    """True si la URL es https://(www.)youtube.com/watch?v=<11 chars>."""
    if not isinstance(url, str):
        return False
    return bool(WATCH_URL_RE.match(url))


def _extract_canonical_watch_id(html: str) -> str | None:
    for tag_match in _LINK_TAG_RE.finditer(html):
        tag = tag_match.group(0)
        if not _REL_CANONICAL_RE.search(tag):
            continue
        href_match = _HREF_RE.search(tag)
        if not href_match:
            continue
        watch_match = WATCH_URL_RE.match(href_match.group(1))
        if not watch_match:
            return None
        return watch_match.group(2)
    return None


def resolve_live_watch_url(stream_url) -> str | None:
    """Resuelve ``https://www.youtube.com/@canal/live`` a ``watch?v=<id>``.

    Solo realiza petición si ``is_live_channel_url(stream_url)`` es True.
    Usa ``safe_get`` (anti-SSRF, sin redirects, timeout 5 s, tope 3 MB) y
    extrae el id exclusivamente del ``<link rel="canonical">``. Cualquier fallo
    de red, tamaño o ausencia de directo en curso devuelve ``None``.
    """
    if not is_live_channel_url(stream_url):
        return None

    handle = LIVE_CHANNEL_RE.match(stream_url).group(2)
    url = f'https://www.youtube.com/@{handle}/live'
    try:
        raw = safe_get(url, allowed_hosts=['www.youtube.com'], timeout=5, max_bytes=3_000_000, headers={
            'User-Agent': _USER_AGENT,
            'Accept-Language': 'es-ES,es;q=0.9',
            # Desde una IP europea YouTube redirige a consent.youtube.com y safe_get no
            # sigue redirects; esta cookie de consentimiento evita ese 302.
            'Cookie': 'SOCS=CAI',
        })
        html = raw.decode('utf-8', errors='replace')
        video_id = _extract_canonical_watch_id(html)
        if not video_id:
            return None
        return f'https://www.youtube.com/watch?v={video_id}'
    except Exception as exc:
        logger.warning(
            'No se pudo resolver el directo de YouTube: %s',
            exc.__class__.__name__,
        )
        return None
