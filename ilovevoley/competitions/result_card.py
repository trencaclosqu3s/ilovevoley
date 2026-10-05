"""Generación on-demand de tarjetas PNG de resultado de partido."""

from __future__ import annotations

import logging
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Callable, Iterable

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from ilovevoley.core.security import safe_get

from .services.sets import extract_set_scores

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
        photo_letterbox=False,
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
        photo_letterbox=True,
    ),
}

_STATIC = Path(__file__).resolve().parents[1] / 'static'
_FONT_REGULAR = _STATIC / 'fonts' / 'SourceSans3-Regular.ttf'
_FONT_BOLD = _STATIC / 'fonts' / 'SourceSans3-Bold.ttf'
_PLACEHOLDER = _STATIC / 'images' / 'crest_placeholder.png'
_LOGO_ISOTYPE = _STATIC / 'images' / 'logo_isotype_white.png'

MARGIN = 80
NAME_GAP = 60
NAME_FONT_SIZE = 42

DARK_TEXT = (26, 26, 26)
WHITE = (255, 255, 255)

LogoFetcher = Callable[[str | None], bytes | None]


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


def _contain_fit(image: Image.Image, width: int, height: int) -> Image.Image:
    """Escala `image` para caber entera en width×height, como CSS object-fit: contain."""
    ratio = min(width / image.width, height / image.height)
    new_size = (max(1, round(image.width * ratio)), max(1, round(image.height * ratio)))
    return image.resize(new_size, Image.Resampling.LANCZOS)


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
    # Sin esto, el degradado de 8 bits se ve "escalonado" a tamaño real (aunque
    # una miniatura reescalada lo disimule al promediar píxeles).
    return _dither(image)


def _dither(image: Image.Image, amount: float = 0.05) -> Image.Image:
    noise = Image.effect_noise(image.size, 40).convert('RGB')
    return Image.blend(image, noise, amount)


def _draw_background_blobs(image: Image.Image, width: int, height: int, metrics: dict):
    """Manchas circulares difuminadas para romper la monotonía del degradado plano."""
    blur_radius = 24

    top_size, top_x, top_y = metrics['blob_top']
    top_alpha = Image.new('L', (top_size, top_size), 0)
    ImageDraw.Draw(top_alpha).ellipse([0, 0, top_size, top_size], fill=26)
    top_alpha = top_alpha.filter(ImageFilter.GaussianBlur(blur_radius))
    image.paste(Image.new('RGB', (top_size, top_size), (255, 255, 255)), (top_x, top_y), top_alpha)

    bottom_size, right_inset, bottom_inset = metrics['blob_bottom']
    bottom_alpha = Image.new('L', (bottom_size, bottom_size), 0)
    ImageDraw.Draw(bottom_alpha).ellipse([0, 0, bottom_size, bottom_size], fill=26)
    bottom_alpha = bottom_alpha.filter(ImageFilter.GaussianBlur(blur_radius))
    bottom_pos = (width - bottom_size + right_inset, height - bottom_size + bottom_inset)
    image.paste(Image.new('RGB', (bottom_size, bottom_size), (0, 0, 0)), bottom_pos, bottom_alpha)


def _photo_background(
    photo: bytes, width: int, height: int, primary, secondary, metrics: dict
) -> Image.Image:
    with Image.open(BytesIO(photo)) as raw:
        source = raw.convert('RGB')

        # En vertical (Story) una foto más ancha que el lienzo se encuadra entera
        # (contain) y los márgenes superior/inferior se rellenan con el degradado
        # del tenant, en vez de recortar los laterales (issue #347).
        if metrics['photo_letterbox'] and source.width / source.height > width / height:
            image = _gradient_background(width, height, primary, secondary, metrics)
            fitted = _contain_fit(source, width, height)
            image.paste(fitted, ((width - fitted.width) // 2, (height - fitted.height) // 2))
        else:
            image = _cover_crop(source, width, height)

    scrim_top = metrics['scrim_top']
    scrim_bottom = metrics['scrim_bottom']
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


@lru_cache(maxsize=4)
def _cached_isotype(path: Path, height: int) -> Image.Image:
    with Image.open(path) as raw:
        image = raw.convert('RGBA')
    ratio = height / image.height
    new_width = max(1, round(image.width * ratio))
    return image.resize((new_width, height), Image.Resampling.LANCZOS)


def _load_footer_isotype(height: int) -> Image.Image | None:
    if not _LOGO_ISOTYPE.exists():
        return None
    try:
        return _cached_isotype(_LOGO_ISOTYPE, height)
    except (OSError, ValueError) as exc:
        logger.warning('No se pudo cargar el isotipo de footer %s: %s', _LOGO_ISOTYPE, exc)
        return None


def _measure_footer(
    draw: ImageDraw.ImageDraw, font, *, icon_height: int = 24, gap: int = 10
) -> tuple[int, int, Image.Image | None, tuple[int, int, int, int]]:
    text = 'ilovevoley.es'
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_w = text_bbox[2] - text_bbox[0]
    text_h = text_bbox[3] - text_bbox[1]
    isotype = _load_footer_isotype(icon_height)
    if isotype is not None:
        total_w = isotype.width + gap + text_w
        footer_h = max(isotype.height, text_h)
    else:
        total_w = text_w
        footer_h = text_h
    return total_w, footer_h, isotype, text_bbox


def _draw_footer(
    draw: ImageDraw.ImageDraw,
    image: Image.Image,
    *,
    width: int,
    y: int,
    font,
    text_color=WHITE,
    gap: int = 10,
    icon_height: int = 24,
    measured: tuple[int, int, Image.Image | None, tuple[int, int, int, int]] | None = None,
) -> int:
    total_width, footer_height, isotype, text_bbox = (
        measured
        if measured is not None
        else _measure_footer(draw, font, icon_height=icon_height, gap=gap)
    )
    text = 'ilovevoley.es'
    text_h = text_bbox[3] - text_bbox[1]

    if isotype is not None:
        start_x = (width - total_width) // 2
        icon_y = y + (footer_height - isotype.height) // 2
        image.paste(isotype, (start_x, icon_y), isotype)

        text_x = start_x + isotype.width + gap
        text_y = y + (footer_height - text_h) // 2 - text_bbox[1]
        draw.text((text_x, text_y), text, font=font, fill=text_color)
    else:
        start_x = (width - total_width) // 2
        draw.text((start_x, y - text_bbox[1]), text, font=font, fill=text_color)

    return footer_height


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
        raise ValueError(_('format inválido: %(format)s') % {'format': card_format})
    if card_style not in CARD_STYLES:
        raise ValueError(_('estilo inválido: %(style)s') % {'style': card_style})
    if card_style == 'marco' and not photo:
        raise ValueError(_('el estilo "marco" requiere una foto'))

    width, height = CARD_SIZES[card_format]
    metrics = _FORMAT_METRICS[card_format]
    primary = _hex_to_rgb(getattr(organization, 'primary_color', None))
    secondary = _hex_to_rgb(
        getattr(organization, 'secondary_color', None) or '', default=primary
    )

    if card_style == 'marco':
        try:
            image = _photo_background(
                photo, width, height, primary, secondary, metrics
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
        _unused_width, sets_height = _sets_row_size(draw, set_list, font_pill, 20, 9, 14)
        footer_font = font_xs
        footer_measured = _measure_footer(draw, footer_font)
        _footer_w, footer_height, _isotype, _bbox = footer_measured

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
        _draw_footer(
            draw, image, width=width, y=footer_y, font=footer_font, text_color=WHITE,
            measured=footer_measured,
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
        _unused_width, sets_height = _sets_row_size(draw, set_list, font_pill, 20, 9, 14)
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

        footer_measured = _measure_footer(draw, font_xs)
        _footer_w, footer_height, _isotype, _bbox = footer_measured
        footer_y = height - card_pad - footer_height
        _draw_footer(
            draw, image, width=width, y=footer_y, font=font_xs, text_color=WHITE,
            measured=footer_measured,
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
