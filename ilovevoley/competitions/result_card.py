"""Generación on-demand de tarjetas PNG de resultado de partido."""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Callable, Iterable

from django.conf import settings
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont
from unidecode import unidecode

from ilovevoley.core.security import safe_get

logger = logging.getLogger(__name__)

CARD_SIZES = {
    'square': (1080, 1080),
    'story': (1080, 1920),
}

_STATIC = Path(__file__).resolve().parents[1] / 'static'
_FONT_REGULAR = _STATIC / 'fonts' / 'SourceSans3-Regular.ttf'
_FONT_BOLD = _STATIC / 'fonts' / 'SourceSans3-Bold.ttf'
_PLACEHOLDER = _STATIC / 'images' / 'crest_placeholder.png'

MARGIN = 80
NAME_GAP = 60
NAME_FONT_SIZE = 42

LogoFetcher = Callable[[str | None], bytes | None]


def extract_set_scores(
    lineup_data: dict, home_name: str, away_name: str
) -> list[tuple[int, int]]:
    """Extrae (pts_local, pts_visitante) por set emparejando por nombre."""

    def words(value: str) -> set[str]:
        normalized = unidecode(value or '').replace('-', ' ')
        return {word.lower() for word in normalized.split() if word}

    home_words, away_words = words(home_name), words(away_name)
    scores: list[tuple[int, int]] = []
    for set_data in lineup_data.get('sets') or []:
        home_points = away_points = None
        for team in set_data.get('teams') or []:
            points = team.get('points')
            if points is None:
                continue
            name_words = words(team.get('name') or '')
            home_match = len(name_words & home_words)
            away_match = len(name_words & away_words)
            if home_match > away_match:
                home_points = int(points)
            elif away_match > home_match:
                away_points = int(points)
        if home_points is not None and away_points is not None:
            scores.append((home_points, away_points))
    return scores


def fetch_logo_bytes(url: str | None, *, timeout: float = 5) -> bytes | None:
    if not url:
        return None
    try:
        return safe_get(
            url,
            allowed_hosts=settings.ACTA_ALLOWED_HOSTS,
            timeout=timeout,
            max_bytes=2 * 1024 * 1024,
        )
    except Exception as exc:
        logger.warning('No se pudo descargar logo %s: %s', url, exc)
        return None


def _load_font(path: Path, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(path), size=size)
    except OSError:
        return ImageFont.load_default()


def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    font_path: Path,
    size: int,
    max_width: int,
    min_size: int = 28,
):
    """Ajusta el texto a `max_width` reduciendo cuerpo y, si no basta, recortando."""
    text = text or ''
    font = _load_font(font_path, size)
    while size > min_size and _text_width(draw, text, font) > max_width:
        size -= 2
        font = _load_font(font_path, size)
    if _text_width(draw, text, font) <= max_width:
        return text, font

    truncated = text
    while truncated and _text_width(draw, f'{truncated}…', font) > max_width:
        truncated = truncated[:-1]
    return f'{truncated.rstrip()}…', font


def _hex_to_rgb(
    value: str, default: tuple[int, int, int] = (155, 127, 191)
) -> tuple[int, int, int]:
    raw = (value or '').strip().lstrip('#')
    if len(raw) != 6:
        return default
    try:
        return tuple(int(raw[index : index + 2], 16) for index in (0, 2, 4))
    except ValueError:
        return default


def _open_logo(data: bytes | None, size: int) -> Image.Image:
    if data:
        try:
            image = Image.open(BytesIO(data)).convert('RGBA')
            image.thumbnail((size, size), Image.Resampling.LANCZOS)
            return image
        except (OSError, ValueError):
            pass
    with Image.open(_PLACEHOLDER) as placeholder_raw:
        placeholder = placeholder_raw.convert('RGBA')
    placeholder.thumbnail((size, size), Image.Resampling.LANCZOS)
    return placeholder


def _org_logo_bytes(organization) -> bytes | None:
    logo = getattr(organization, 'logo', None)
    if not logo:
        return None
    try:
        logo.open('rb')
        try:
            return logo.read()
        finally:
            logo.close()
    except Exception:
        return None


def render_result_card(
    *,
    match,
    organization,
    card_format: str = 'square',
    sets: Iterable[tuple[int, int]] | None = None,
    logo_fetcher: LogoFetcher | None = None,
) -> bytes:
    if card_format not in CARD_SIZES:
        raise ValueError(f'format inválido: {card_format}')
    width, height = CARD_SIZES[card_format]
    primary = _hex_to_rgb(getattr(organization, 'primary_color', None))
    secondary = _hex_to_rgb(
        getattr(organization, 'secondary_color', None) or '', default=primary
    )

    # Degradado vertical: imagen 1×2 escalada con interpolación bilineal.
    gradient_seed = Image.new('RGB', (1, 2), primary)
    gradient_seed.putpixel((0, 1), secondary)
    image = gradient_seed.resize((width, height), Image.Resampling.BILINEAR)
    draw = ImageDraw.Draw(image)

    fetcher = logo_fetcher or fetch_logo_bytes
    crest_size = 220 if card_format == 'square' else 280
    home_logo_url = getattr(getattr(match, 'home_team', None), 'display_logo', None)
    away_logo_url = getattr(getattr(match, 'away_team', None), 'display_logo', None)
    try:
        home_logo = fetcher(home_logo_url)
    except Exception:
        home_logo = None
    try:
        away_logo = fetcher(away_logo_url)
    except Exception:
        away_logo = None
    home_crest = _open_logo(home_logo, crest_size)
    away_crest = _open_logo(away_logo, crest_size)

    font_lg = _load_font(_FONT_BOLD, 96 if card_format == 'square' else 110)
    font_sm = _load_font(_FONT_REGULAR, 32)
    font_xs = _load_font(_FONT_REGULAR, 26)
    white = (255, 255, 255)

    org_bytes = _org_logo_bytes(organization)
    y = 60 if card_format == 'square' else 120
    if org_bytes:
        org_image = _open_logo(org_bytes, 72)
        image.paste(org_image, (48, y), org_image)
    league_name = getattr(getattr(match, 'league', None), 'name', '') or ''
    date_str = timezone.localtime(match.match_date).strftime('%d/%m/%Y')
    draw.text((140, y + 10), league_name, font=font_sm, fill=white)
    draw.text((140, y + 50), date_str, font=font_xs, fill=white)

    center_y = height // 2 - crest_size // 2
    score = f'{match.home_score} - {match.away_score}'
    score_bbox = draw.textbbox((0, 0), score, font=font_lg)
    score_width = score_bbox[2] - score_bbox[0]
    score_x = (width - score_width) // 2
    image.paste(home_crest, (MARGIN, center_y), home_crest)
    image.paste(away_crest, (width - MARGIN - away_crest.width, center_y), away_crest)
    draw.text(
        (score_x, center_y + crest_size // 2 - 50),
        score,
        font=font_lg,
        fill=white,
    )

    name_y = center_y + crest_size + 24
    max_name_width = (width - 2 * MARGIN - NAME_GAP) // 2
    home_name, home_font = _fit_text(
        draw,
        match.home_team_display,
        font_path=_FONT_BOLD,
        size=NAME_FONT_SIZE,
        max_width=max_name_width,
    )
    away_name, away_font = _fit_text(
        draw,
        match.away_team_display,
        font_path=_FONT_BOLD,
        size=NAME_FONT_SIZE,
        max_width=max_name_width,
    )
    draw.text((MARGIN, name_y), home_name, font=home_font, fill=white)
    draw.text(
        (width - MARGIN - _text_width(draw, away_name, away_font), name_y),
        away_name,
        font=away_font,
        fill=white,
    )

    set_list = list(sets or [])
    if set_list:
        sets_str = '  ·  '.join(f'{home}-{away}' for home, away in set_list)
        sets_bbox = draw.textbbox((0, 0), sets_str, font=font_sm)
        draw.text(
            ((width - (sets_bbox[2] - sets_bbox[0])) // 2, name_y + 70),
            sets_str,
            font=font_sm,
            fill=white,
        )

    footer = 'ilovevoley'
    footer_bbox = draw.textbbox((0, 0), footer, font=font_xs)
    draw.text(
        ((width - (footer_bbox[2] - footer_bbox[0])) // 2, height - 80),
        footer,
        font=font_xs,
        fill=white,
    )

    buffer = BytesIO()
    image.save(buffer, format='PNG', optimize=True)
    return buffer.getvalue()
