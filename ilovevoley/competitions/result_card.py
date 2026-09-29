"""Generación on-demand de tarjetas PNG de resultado de partido."""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Callable, Iterable

from django.conf import settings
from django.utils import timezone
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
from unidecode import unidecode

from ilovevoley.core.security import safe_get

logger = logging.getLogger(__name__)

CARD_SIZES = {
    'square': (1080, 1080),
    'story': (1080, 1920),
}

CARD_STYLES = ('completa', 'marco')

# Métricas específicas de cada formato para las dos variantes visuales (issue #241).
_FORMAT_METRICS = {
    'square': dict(
        crest_size=190,
        header_y=60,
        score_font_size=80,
        card_pad=48,
        scrim_top=220,
        scrim_bottom=560,
        frame_outer=12,
        frame_inner=5,
        blob_top=(420, -120, -120),
        blob_bottom=(360, 100, 100),
    ),
    'story': dict(
        crest_size=240,
        header_y=120,
        score_font_size=100,
        card_pad=64,
        scrim_top=420,
        scrim_bottom=820,
        frame_outer=14,
        frame_inner=6,
        blob_top=(640, -160, -180),
        blob_bottom=(520, 140, 140),
    ),
}

_STATIC = Path(__file__).resolve().parents[1] / 'static'
_FONT_REGULAR = _STATIC / 'fonts' / 'SourceSans3-Regular.ttf'
_FONT_BOLD = _STATIC / 'fonts' / 'SourceSans3-Bold.ttf'
_PLACEHOLDER = _STATIC / 'images' / 'crest_placeholder.png'

MARGIN = 80
NAME_GAP = 60
NAME_FONT_SIZE = 42

DARK_TEXT = (26, 26, 26)
WHITE = (255, 255, 255)

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


def _file_field_bytes(field) -> bytes | None:
    """Lee los bytes de un FileField/ImageField de Django, si tiene fichero."""
    if not field:
        return None
    try:
        field.open('rb')
        try:
            return field.read()
        finally:
            field.close()
    except Exception:
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
    return _file_field_bytes(getattr(organization, 'logo', None))


def _cover_crop(image: Image.Image, width: int, height: int) -> Image.Image:
    """Escala y recorta `image` para cubrir width×height, como CSS object-fit: cover."""
    src_ratio = image.width / image.height
    target_ratio = width / height
    if src_ratio > target_ratio:
        new_height = height
        new_width = round(height * src_ratio)
    else:
        new_width = width
        new_height = round(width / src_ratio)
    resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    left = (new_width - width) // 2
    top = (new_height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _vertical_alpha_gradient(width: int, height: int, top_alpha: int, bottom_alpha: int):
    seed = Image.new('L', (1, 2))
    seed.putpixel((0, 0), top_alpha)
    seed.putpixel((0, 1), bottom_alpha)
    return seed.resize((width, height), Image.Resampling.BILINEAR)


def _gradient_background(
    width: int, height: int, primary, secondary, metrics: dict | None = None
) -> Image.Image:
    # Degradado vertical: imagen 1×2 escalada con interpolación bilineal.
    seed = Image.new('RGB', (1, 2), primary)
    seed.putpixel((0, 1), secondary)
    image = seed.resize((width, height), Image.Resampling.BILINEAR)
    if metrics:
        _draw_background_blobs(image, width, height, metrics)
    return image


def _draw_background_blobs(image: Image.Image, width: int, height: int, metrics: dict):
    """Manchas circulares difuminadas para romper la monotonía del degradado plano."""
    top_size, top_x, top_y = metrics['blob_top']
    top_alpha = Image.new('L', (top_size, top_size), 0)
    ImageDraw.Draw(top_alpha).ellipse([0, 0, top_size, top_size], fill=26)
    image.paste(Image.new('RGB', (top_size, top_size), (255, 255, 255)), (top_x, top_y), top_alpha)

    bottom_size, right_inset, bottom_inset = metrics['blob_bottom']
    bottom_alpha = Image.new('L', (bottom_size, bottom_size), 0)
    ImageDraw.Draw(bottom_alpha).ellipse([0, 0, bottom_size, bottom_size], fill=26)
    bottom_pos = (width - bottom_size + right_inset, height - bottom_size + bottom_inset)
    image.paste(Image.new('RGB', (bottom_size, bottom_size), (0, 0, 0)), bottom_pos, bottom_alpha)


def _photo_background(
    photo: bytes, width: int, height: int, primary, scrim_top: int, scrim_bottom: int
) -> Image.Image:
    with Image.open(BytesIO(photo)) as raw:
        image = _cover_crop(raw.convert('RGB'), width, height)

    top_mask = _vertical_alpha_gradient(width, scrim_top, 190, 0)
    image.paste(Image.new('RGB', (width, scrim_top), primary), (0, 0), top_mask)

    bottom_mask = _vertical_alpha_gradient(width, scrim_bottom, 0, 220)
    image.paste(
        Image.new('RGB', (width, scrim_bottom), primary), (0, height - scrim_bottom), bottom_mask
    )
    return image


def _draw_frame(draw: ImageDraw.ImageDraw, width: int, height: int, outer, inner, secondary, primary):
    draw.rectangle([0, 0, width - 1, height - 1], outline=secondary, width=outer)
    inset = outer
    draw.rectangle(
        [inset, inset, width - 1 - inset, height - 1 - inset], outline=primary, width=inner
    )


def _draw_header(draw, image, *, organization, match, x, y, font_sm, font_xs, text_color):
    org_bytes = _org_logo_bytes(organization)
    if org_bytes:
        org_image = _open_logo(org_bytes, 72)
        image.paste(org_image, (x, y), org_image)
    league_name = getattr(getattr(match, 'league', None), 'name', '') or ''
    date_str = timezone.localtime(match.match_date).strftime('%d/%m/%Y')
    draw.text((x + 92, y + 10), league_name, font=font_sm, fill=text_color)
    draw.text((x + 92, y + 50), date_str, font=font_xs, fill=text_color)


def _fit_team_names(draw, match, max_width: int):
    home_name, home_font = _fit_text(
        draw, match.home_team_display, font_path=_FONT_BOLD, size=NAME_FONT_SIZE,
        max_width=max_width,
    )
    away_name, away_font = _fit_text(
        draw, match.away_team_display, font_path=_FONT_BOLD, size=NAME_FONT_SIZE,
        max_width=max_width,
    )
    row_height = max(_text_height(draw, home_name, home_font), _text_height(draw, away_name, away_font))
    return home_name, home_font, away_name, away_font, row_height


def _sets_row_size(draw, set_list, font, pad_x: int, pad_y: int, gap: int) -> tuple[int, int]:
    if not set_list:
        return 0, 0
    height = 0
    total_width = 0
    for index, (home, away) in enumerate(set_list):
        bbox = draw.textbbox((0, 0), f'{home}-{away}', font=font)
        width = (bbox[2] - bbox[0]) + 2 * pad_x
        height = max(height, (bbox[3] - bbox[1]) + 2 * pad_y)
        total_width += width + (gap if index else 0)
    return total_width, height


def _draw_sets_row(draw, set_list, font, *, center_x, y, bg, text_color):
    pad_x, pad_y, gap = 20, 9, 14
    total_width, height = _sets_row_size(draw, set_list, font, pad_x, pad_y, gap)
    x = center_x - total_width // 2
    for home, away in set_list:
        text = f'{home}-{away}'
        bbox = draw.textbbox((0, 0), text, font=font)
        width = (bbox[2] - bbox[0]) + 2 * pad_x
        draw.rounded_rectangle([x, y, x + width, y + height], radius=height // 2, fill=bg)
        draw.text((x + pad_x, y + pad_y - bbox[1]), text, font=font, fill=text_color)
        x += width + gap
    return height


def render_result_card(
    *,
    match,
    organization,
    card_format: str = 'square',
    card_style: str = 'completa',
    sets: Iterable[tuple[int, int]] | None = None,
    photo: bytes | None = None,
    logo_fetcher: LogoFetcher | None = None,
) -> bytes:
    if card_format not in CARD_SIZES:
        raise ValueError(f'format inválido: {card_format}')
    if card_style not in CARD_STYLES:
        raise ValueError(f'estilo inválido: {card_style}')
    if card_style == 'marco' and not photo:
        raise ValueError('el estilo "marco" requiere una foto')

    width, height = CARD_SIZES[card_format]
    metrics = _FORMAT_METRICS[card_format]
    primary = _hex_to_rgb(getattr(organization, 'primary_color', None))
    secondary = _hex_to_rgb(
        getattr(organization, 'secondary_color', None) or '', default=primary
    )

    if card_style == 'marco':
        try:
            image = _photo_background(
                photo, width, height, primary, metrics['scrim_top'], metrics['scrim_bottom']
            )
        except (OSError, ValueError) as exc:
            logger.warning('Foto de marco no válida, usando degradado: %s', exc)
            image = _gradient_background(width, height, primary, secondary, metrics)
            card_style = 'completa'
    else:
        image = _gradient_background(width, height, primary, secondary, metrics)
    draw = ImageDraw.Draw(image)

    fetcher = logo_fetcher or fetch_logo_bytes
    crest_size = metrics['crest_size']
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

    font_lg = _load_font(_FONT_BOLD, metrics['score_font_size'])
    font_sm = _load_font(_FONT_REGULAR, 32)
    font_xs = _load_font(_FONT_REGULAR, 26)
    font_pill = _load_font(_FONT_REGULAR, 26)

    score = f'{match.home_score} - {match.away_score}'
    set_list = list(sets or [])

    if card_style == 'marco':
        _draw_header(
            draw, image, organization=organization, match=match,
            x=48, y=metrics['header_y'], font_sm=font_sm, font_xs=font_xs, text_color=WHITE,
        )

        side_x = MARGIN + 20
        name_max_width = (width - 2 * side_x - NAME_GAP) // 2
        home_name, home_font, away_name, away_font, name_row_height = _fit_team_names(
            draw, match, name_max_width
        )
        _, sets_height = _sets_row_size(draw, set_list, font_pill, 20, 9, 14)
        footer_font = font_xs
        footer_bbox = draw.textbbox((0, 0), 'ilovevoley', font=footer_font)
        footer_height = footer_bbox[3] - footer_bbox[1]

        content_bottom = height - metrics['card_pad']
        footer_y = content_bottom - footer_height
        sets_y = footer_y - 24 - sets_height if set_list else footer_y
        names_y = sets_y - 20 - name_row_height
        crest_top = names_y - 16 - crest_size

        _paste_crest_circle(image, home_crest, crest_size, side_x, crest_top)
        _paste_crest_circle(
            image, away_crest, crest_size, width - side_x - crest_size, crest_top
        )
        _draw_score(
            draw, score, font_lg, center_x=width // 2,
            center_y=crest_top + crest_size // 2, color=WHITE,
        )
        draw.text((side_x, names_y), home_name, font=home_font, fill=WHITE)
        draw.text(
            (width - side_x - _text_width(draw, away_name, away_font), names_y),
            away_name, font=away_font, fill=WHITE,
        )
        if set_list:
            pill_bg_marco = tuple(channel * 55 // 100 for channel in primary)
            _draw_sets_row(
                draw, set_list, font_pill, center_x=width // 2, y=sets_y,
                bg=pill_bg_marco, text_color=WHITE,
            )
        draw.text(
            ((width - (footer_bbox[2] - footer_bbox[0])) // 2, footer_y),
            'ilovevoley', font=footer_font, fill=WHITE,
        )
        _draw_frame(
            draw, width, height, metrics['frame_outer'], metrics['frame_inner'], secondary, primary
        )
    else:
        _draw_header(
            draw, image, organization=organization, match=match,
            x=48, y=metrics['header_y'], font_sm=font_sm, font_xs=font_xs, text_color=WHITE,
        )

        card_pad = metrics['card_pad']
        card_interior_width = (width - 2 * MARGIN) - 2 * card_pad
        name_max_width = (card_interior_width - NAME_GAP) // 2
        home_name, home_font, away_name, away_font, name_row_height = _fit_team_names(
            draw, match, name_max_width
        )
        _, sets_height = _sets_row_size(draw, set_list, font_pill, 20, 9, 14)
        card_height = (
            2 * card_pad + crest_size + 24 + name_row_height
            + (24 + sets_height if set_list else 0)
        )
        header_bottom = metrics['header_y'] + 100
        footer_top = height - metrics['card_pad']
        card_top = header_bottom + (footer_top - header_bottom - card_height) // 2
        card_left, card_right = MARGIN, width - MARGIN
        card_box = [card_left, card_top, card_right, card_top + card_height]

        _draw_card_shadow(image, card_box, radius=40)
        draw.rounded_rectangle(card_box, radius=40, fill=WHITE)

        crest_row_y = card_top + card_pad
        image.paste(home_crest, (card_left + card_pad, crest_row_y), home_crest)
        image.paste(
            away_crest, (card_right - card_pad - crest_size, crest_row_y), away_crest
        )
        _draw_score(
            draw, score, font_lg, center_x=width // 2,
            center_y=crest_row_y + crest_size // 2, color=primary,
        )

        names_y = crest_row_y + crest_size + 24
        draw.text((card_left + card_pad, names_y), home_name, font=home_font, fill=DARK_TEXT)
        draw.text(
            (card_right - card_pad - _text_width(draw, away_name, away_font), names_y),
            away_name, font=away_font, fill=DARK_TEXT,
        )
        if set_list:
            sets_y = names_y + name_row_height + 24
            pill_bg = tuple(min(255, channel + (255 - channel) * 9 // 10) for channel in primary)
            _draw_sets_row(
                draw, set_list, font_pill, center_x=width // 2, y=sets_y,
                bg=pill_bg, text_color=primary,
            )

        footer_bbox = draw.textbbox((0, 0), 'ilovevoley', font=font_xs)
        draw.text(
            ((width - (footer_bbox[2] - footer_bbox[0])) // 2, height - 60),
            'ilovevoley', font=font_xs, fill=WHITE,
        )

    buffer = BytesIO()
    image.convert('RGB').save(buffer, format='PNG', optimize=True)
    return buffer.getvalue()


def _text_height(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    bbox = draw.textbbox((0, 0), text or ' ', font=font)
    return bbox[3] - bbox[1]


def _draw_score(draw, score: str, font, *, center_x: int, center_y: int, color):
    bbox = draw.textbbox((0, 0), score, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    draw.text(
        (center_x - width // 2, center_y - height // 2 - bbox[1]), score, font=font, fill=color
    )


def _paste_crest_circle(image: Image.Image, crest: Image.Image, size: int, x: int, y: int):
    """Pega el escudo sobre un disco blanco semitransparente, recortado a círculo.

    Un escudo rectangular con fondo opaco puede llenar toda la caja size×size;
    sin este recorte, sus esquinas sobresaldrían del disco.
    """
    backdrop = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(backdrop).ellipse([0, 0, size, size], fill=(255, 255, 255, 235))
    offset = ((size - crest.width) // 2, (size - crest.height) // 2)
    backdrop.paste(crest, offset, crest)
    circle_mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(circle_mask).ellipse([0, 0, size, size], fill=255)
    backdrop.putalpha(ImageChops.multiply(backdrop.getchannel('A'), circle_mask))
    image.paste(backdrop, (x, y), backdrop)


def _draw_card_shadow(image: Image.Image, box, radius: int):
    shadow = Image.new('RGBA', image.size, (0, 0, 0, 0))
    shadow_box = [box[0], box[1] + 14, box[2], box[3] + 14]
    ImageDraw.Draw(shadow).rounded_rectangle(shadow_box, radius=radius, fill=(0, 0, 0, 90))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    image.paste(Image.new('RGB', image.size, (0, 0, 0)), (0, 0), shadow)
