"""PNG Story de cada pantalla del Wrapped (#458), con el estilo del cromo."""
from io import BytesIO

from PIL import Image, ImageDraw

from ilovevoley.competitions.result_card import (
    _FONT_BOLD,
    _FONT_REGULAR,
    _FORMAT_METRICS,
    CARD_SIZES,
    _cover_crop,
    _draw_footer,
    _fit_text,
    _gradient_background,
    _hex_to_rgb,
    _load_font as _font,
    _measure_footer,
    _open_logo,
    _org_logo_bytes,
    _paste_crest_circle,
)
from ilovevoley.rosters.player_card import _BOTTOM, _PAD_X, _TOP, _text


def _centered(draw, width, y, text, font_path, size, max_width, fill='white', min_size=28):
    text, font = _fit_text(draw, text, font_path=font_path, size=size, max_width=max_width, min_size=min_size)
    _text(draw, ((width - draw.textlength(text, font=font)) / 2, y), text, font, fill)


def _draw_rival(image, width, top, inner_w, screen, organization, rival_logo):
    """Escudo del club del jugador frente al del rival más repetido, con su nombre debajo."""
    size, gap = 300, 140
    left = (width - (2 * size + gap)) // 2
    for logo, x in ((_org_logo_bytes(organization), left), (rival_logo, left + size + gap)):
        _paste_crest_circle(image, _open_logo(logo, int(size * 0.8)), size, x, top)
    draw = ImageDraw.Draw(image)
    _centered(draw, width, top + size // 2 - 36, 'VS', _FONT_BOLD, 64, gap)
    _centered(draw, width, top + size + 60, screen.value, _FONT_BOLD, 64, inner_w, min_size=36)
    _centered(draw, width, top + size + 170, screen.subtitle, _FONT_REGULAR, 56, inner_w)


def render_wrapped_screen(*, organization, screen, photo=None, rival_logo=None) -> bytes:
    width, height = CARD_SIZES['story']
    primary = _hex_to_rgb(getattr(organization, 'primary_color', None))
    secondary = _hex_to_rgb(getattr(organization, 'secondary_color', None) or '', default=primary)
    image = _gradient_background(width, height, primary, secondary, _FORMAT_METRICS['story']).convert('RGBA')
    draw = ImageDraw.Draw(image)
    inner_w = width - 2 * _PAD_X

    logo = _org_logo_bytes(organization)
    if logo:
        _paste_crest_circle(image, _open_logo(logo, 90), 112, _PAD_X, _TOP)

    footer = _measure_footer(draw, _font(_FONT_BOLD, 30), icon_height=30, gap=12)
    footer_y = height - _BOTTOM - footer[1]
    _draw_footer(draw, image, width=width, y=footer_y, font=_font(_FONT_BOLD, 30), gap=12,
                 icon_height=30, measured=footer)

    if screen.kind == 'top_photo':
        _centered(draw, width, _TOP + 160, screen.title, _FONT_BOLD, 64, inner_w)
        top, bottom = _TOP + 280, footer_y - 60
        if photo:
            box = _cover_crop(Image.open(BytesIO(photo)).convert('RGB'), inner_w, bottom - top)
            image.paste(box, (_PAD_X, top))
    else:
        y = height // 2 - 260
        if screen.caption:
            _centered(draw, width, y - 110, screen.caption.upper(), _FONT_BOLD, 30, inner_w, min_size=20)
        _centered(draw, width, y, screen.title, _FONT_REGULAR, 56, inner_w)
        if screen.kind == 'rival':
            _draw_rival(image, width, y + 130, inner_w, screen, organization, rival_logo)
        else:
            if screen.value:
                _centered(draw, width, y + 110, screen.value, _FONT_BOLD, 260, inner_w, min_size=48)
            if screen.subtitle:
                _centered(draw, width, y + (400 if screen.value.isdigit() else 300), screen.subtitle,
                          _FONT_REGULAR, 56, inner_w)

    buffer = BytesIO()
    image.convert('RGB').save(buffer, 'PNG')
    return buffer.getvalue()
