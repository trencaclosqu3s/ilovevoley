"""Cromo del jugador (#457): perfil de la temporada sacado de las actas y su imagen Story.

El perfil siempre es positivo y nunca compara con compañeros: cada regla mira al
jugador frente a su propio equipo. Si no se cumple ninguna, se muestra un momento
concreto de la temporada, que siempre es cierto (quien ha jugado poco lo sabe y un
perfil inflado no le sirve). Los textos van en masculino: hoy todos los equipos de
la app lo son; con equipos femeninos, la concordancia saldría de ``Team.gender``.
"""

from io import BytesIO

from django.db.models import Q
from django.template.defaultfilters import date as date_filter
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from PIL import Image, ImageDraw

from ilovevoley.competitions.models import Match, MatchLineup
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
    _vertical_alpha_gradient,
)
from ilovevoley.competitions.services.lineups import _SET_POSITIONS, resolve_acta_team

TALISMAN_MIN_SETS = 15
TALISMAN_MIN_DIFF = 0.10
TIGHT_MIN_WINS = 3
SUB_MIN_SETS = 5
STARTER_MIN_SHARE = 0.8
FIVE_SET_MIN_MATCHES = 3
AWAY_MIN_MATCHES = 5
AWAY_MIN_SHARE = 0.8


def season_facts(person, teams, season):
    """Recorre las actas del equipo en la temporada y cuenta lo que piden los perfiles.

    ``teams`` son los equipos (fases) de la identidad del jugador en el tenant. Los
    totales del equipo cuentan todos sus partidos con acta, no solo los que jugó
    él: así un lesionado no sale como titular fijo con cuatro partidos.
    """
    team_ids = {team.id for team in teams}
    lineups = {
        row.match_id: row
        for row in MatchLineup.objects.filter(
            person=person, team_id__in=team_ids, match__league__season=season,
        )
    }
    facts = dict(
        team_sets=0, team_sets_won=0, sets=0, sets_won=0, starts=0, tight_wins=0,
        sub_sets=0, sub_sets_won=0, comebacks=0, five_setters=0, team_away=0, away=0,
    )
    matches = Match.objects.filter(
        Q(home_team_id__in=team_ids) | Q(away_team_id__in=team_ids),
        league__season=season, status='finished', acta_data__isnull=False,
    ).select_related('home_team', 'away_team')
    for match in matches:
        ours = match.home_team if match.home_team_id in team_ids else match.away_team
        row = lineups.get(match.id)
        jersey = row.jersey_number if row else None
        won_sets = played_here = 0
        results = []
        for index, set_data in enumerate(match.acta_data.get('sets') or []):
            points, rival_points, entries = None, None, []
            for team_data in set_data.get('teams') or []:
                team = resolve_acta_team(team_data.get('name'), match.home_team, match.away_team)
                if team == ours:
                    points, entries = team_data.get('points'), team_data.get('lineup') or []
                else:
                    rival_points = team_data.get('points')
            if points is None or rival_points is None:
                continue
            won = int(points) > int(rival_points)
            results.append(won)
            won_sets += won
            facts['team_sets'] += 1
            facts['team_sets_won'] += won
            if jersey is None:
                continue
            started = any(e.get('number') == jersey and e.get('position') in _SET_POSITIONS for e in entries)
            subbed_in = any((e.get('sub') or {}).get('number') == jersey for e in entries)
            if not (started or subbed_in):
                continue
            played_here += 1
            facts['sets'] += 1
            facts['sets_won'] += won
            facts['starts'] += started
            if won and (int(points) - int(rival_points) == 2 or index == 4):
                facts['tight_wins'] += 1
            if subbed_in and not started:
                facts['sub_sets'] += 1
                facts['sub_sets_won'] += won
        match_won = won_sets * 2 > len(results)
        if ours == match.away_team:
            facts['team_away'] += 1
            facts['away'] += bool(played_here)
        if played_here and match_won and results[:2] == [False, False]:
            facts['comebacks'] += 1
        if played_here and len(results) == 5:
            facts['five_setters'] += 1
    return facts


def pick_profile(facts):
    """Primer perfil que se cumple, en orden de prioridad, o ``None``."""
    sets, team_sets = facts['sets'], facts['team_sets']
    if sets >= TALISMAN_MIN_SETS and team_sets:
        mine, team = facts['sets_won'] / sets, facts['team_sets_won'] / team_sets
        if mine - team >= TALISMAN_MIN_DIFF:
            return 'talisman', _('Talismán'), _('El equipo ganó el %(pct)s %% de los sets que jugó') % {
                'pct': round(mine * 100)}
    if facts['tight_wins'] >= TIGHT_MIN_WINS:
        return 'sangre_fria', _('Sangre fría'), _('En pista en %(n)s sets ajustados que ganó el equipo') % {
            'n': facts['tight_wins']}
    if facts['sub_sets'] >= SUB_MIN_SETS and facts['sub_sets_won'] * 2 > facts['sub_sets']:
        return 'revulsivo', _('Revulsivo'), _('Entró desde el banquillo en %(n)s sets y el equipo ganó %(won)s') % {
            'n': facts['sub_sets'], 'won': facts['sub_sets_won']}
    if team_sets and facts['starts'] >= STARTER_MIN_SHARE * team_sets:
        return 'fijo', _('Fijo en el seis'), _('Titular en %(n)s de los %(total)s sets del equipo') % {
            'n': facts['starts'], 'total': team_sets}
    if facts['comebacks']:
        return 'remontada', _('Remontada'), ngettext(
            'En pista en %(n)s partido que el equipo remontó',
            'En pista en %(n)s partidos que el equipo remontó', facts['comebacks'],
        ) % {'n': facts['comebacks']}
    if facts['five_setters'] >= FIVE_SET_MIN_MATCHES:
        return 'maraton', _('Maratón'), _('Jugó %(n)s partidos a cinco sets') % {'n': facts['five_setters']}
    if facts['away'] >= AWAY_MIN_MATCHES and facts['away'] >= AWAY_MIN_SHARE * facts['team_away']:
        return 'viajero', _('Viajero'), _('Jugó %(n)s de los %(total)s partidos fuera de casa') % {
            'n': facts['away'], 'total': facts['team_away']}
    return None


def season_moment(person, teams, season):
    """Momento por defecto: una victoria en pista, el partido con más sets o el debut."""
    rows = list(
        MatchLineup.objects.filter(person=person, team__in=teams, match__league__season=season)
        .exclude(match__status='withdrawn').select_related('match__home_team', 'match__away_team')
    )

    def score(row):
        match = row.match
        if match.home_score is None or match.away_score is None:
            return None
        home = row.team_id == match.home_team_id
        return (match.home_score, match.away_score) if home else (match.away_score, match.home_score)

    def rival(row):
        match = row.match
        return match.away_team_display if row.team_id == match.home_team_id else match.home_team_display

    def when(row):
        return date_filter(row.match.match_date, 'j \\d\\e F')

    finished = [row for row in rows if row.match.status == 'finished' and score(row)]
    wins = [row for row in finished if row.sets_played and score(row)[0] > score(row)[1]]
    if wins:
        best = max(wins, key=lambda row: (row.sets_played, -(score(row)[0] - score(row)[1])))
        ours, theirs = score(best)
        return _('Victoria %(ours)s-%(theirs)s') % {'ours': ours, 'theirs': theirs}, _(
            'En pista contra %(rival)s el %(date)s') % {'rival': rival(best), 'date': when(best)}
    played = [row for row in rows if row.sets_played]
    if played:
        best = max(played, key=lambda row: row.sets_played)
        return ngettext('%(n)s set en pista', '%(n)s sets en pista', best.sets_played) % {
            'n': best.sets_played}, _('Contra %(rival)s el %(date)s') % {'rival': rival(best), 'date': when(best)}
    called = [row for row in rows if row.is_convocado]
    if called:
        first = min(called, key=lambda row: row.match.match_date)
        return _('Convocado'), _('Primera convocatoria: contra %(rival)s el %(date)s') % {
            'rival': rival(first), 'date': when(first)}
    return None


def card_highlight(person, teams, season):
    """Lo que va en el recuadro del cromo: ``{key, caption, title, text}`` o ``None``."""
    profile = pick_profile(season_facts(person, teams, season))
    if profile:
        key, title, text = profile
        return {'key': key, 'caption': _('Perfil de la temporada'), 'title': title, 'text': text}
    moment = season_moment(person, teams, season)
    if moment:
        title, text = moment
        return {'key': 'momento', 'caption': _('Momento de la temporada'), 'title': title, 'text': text}
    return None


# Iconos en una rejilla de 24×24 (los mismos trazos que el diseño): polilíneas y círculos.
_ICONS = {
    'talisman': ([[(12, 2), (15.1, 8.3), (22, 9.3), (17, 14.2), (18.2, 21), (12, 17.8), (5.8, 21),
                   (7, 14.2), (2, 9.3), (8.9, 8.3), (12, 2)]], []),
    'sangre_fria': ([[(12, 2), (12, 22)], [(4, 6), (20, 18)], [(20, 6), (4, 18)],
                     [(9, 3), (12, 6), (15, 3)], [(9, 21), (12, 18), (15, 21)]], []),
    'revulsivo': ([[(13, 2), (4, 14), (11, 14), (10, 22), (19, 10), (12, 10), (13, 2)]], []),
    'fijo': ([[(12, 2), (20.7, 7), (20.7, 17), (12, 22), (3.3, 17), (3.3, 7), (12, 2)],
              [(12, 8), (12, 16)], [(8.5, 10), (15.5, 14)], [(15.5, 10), (8.5, 14)]], []),
    'remontada': ([[(3, 17), (9, 11), (13, 15), (21, 7)], [(14, 7), (21, 7), (21, 14)]], []),
    'maraton': ([[(12, 7), (12, 12), (15, 15)]], [(12, 12, 9)]),
    'viajero': ([[(6.4, 14.2), (12, 22), (17.6, 14.2)]], [(12, 10, 7), (12, 10, 2.5)]),
    'momento': ([[(5, 21), (5, 4), (17, 4), (14.5, 8), (17, 12), (5, 12)]], []),
}

_PAD_X, _TOP, _BOTTOM, _GAP = 72, 96, 72, 40
_INK = (26, 26, 26)
_MUTED = (89, 89, 89)
_TILE = (255, 255, 255, 36)


def _draw_icon(draw, key, x, y, size, color):
    lines, circles = _ICONS[key]
    scale = size / 24
    stroke = max(2, round(2 * scale))
    for line in lines:
        draw.line([(x + px * scale, y + py * scale) for px, py in line], fill=color, width=stroke, joint='curve')
    for cx, cy, r in circles:
        box = [x + (cx - r) * scale, y + (cy - r) * scale, x + (cx + r) * scale, y + (cy + r) * scale]
        draw.ellipse(box, outline=color, width=stroke)


def _rounded_mask(size, radius):
    mask = Image.new('L', size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return mask


def _text(draw, xy, text, font, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    draw.text((xy[0], xy[1] - bbox[1]), text, font=font, fill=fill)
    return bbox[3] - bbox[1]


def render_player_card(*, organization, person, role, highlight, stats, photo=None) -> bytes:
    """PNG Story (1080×1920) con foto, dorsal, perfil o momento y cifras de las actas.

    ``stats`` es ``None`` cuando no hay actas: entonces no se pinta ni el recuadro
    ni las cifras y la foto ocupa ese espacio.
    """
    width, height = CARD_SIZES['story']
    primary = _hex_to_rgb(getattr(organization, 'primary_color', None))
    secondary = _hex_to_rgb(getattr(organization, 'secondary_color', None) or '', default=primary)
    image = _gradient_background(width, height, primary, secondary, _FORMAT_METRICS['story']).convert('RGBA')
    draw = ImageDraw.Draw(image)
    inner_w = width - 2 * _PAD_X

    # Cabecera: escudo del club, equipo y temporada.
    logo = _org_logo_bytes(organization)
    if logo:
        _paste_crest_circle(image, _open_logo(logo, 90), 112, _PAD_X, _TOP)
    text_x = _PAD_X + (112 + 28 if logo else 0)
    team_name, font = _fit_text(draw, role.identity.core_name, font_path=_FONT_BOLD, size=40,
                                max_width=width - _PAD_X - text_x)
    _text(draw, (text_x, _TOP + 14), team_name, font, 'white')
    season_line = _('Temporada %(season)s') % {'season': role.season.name}
    _text(draw, (text_x, _TOP + 66), season_line, _font(_FONT_REGULAR, 32), (255, 255, 255, 220))

    # De abajo arriba: pie, cifras, recuadro del perfil; la foto se queda el resto.
    footer = _measure_footer(draw, _font(_FONT_BOLD, 30), icon_height=30, gap=12)
    y = height - _BOTTOM - footer[1]
    _draw_footer(draw, image, width=width, y=y, font=_font(_FONT_BOLD, 30), gap=12, icon_height=30,
                 measured=footer)
    if stats is not None:
        y -= _GAP + 34
        caption = _('Partidos oficiales · según actas').upper()
        caption_font = _font(_FONT_BOLD, 28)
        _text(draw, ((width - draw.textlength(caption, font=caption_font)) / 2, y + 2), caption,
              caption_font, 'white')
        y -= 20 + 196
        _draw_stats(image, y, inner_w, stats)
    if highlight is not None:
        y -= _GAP + 216
        _draw_highlight(image, y, inner_w, highlight, primary)
    photo_top = _TOP + 112 + _GAP
    _draw_photo_box(image, (_PAD_X, photo_top, width - _PAD_X, y - _GAP), person, role, photo)

    buffer = BytesIO()
    image.convert('RGB').save(buffer, 'PNG')
    return buffer.getvalue()


def _draw_stats(image, y, inner_w, stats):
    overlay = Image.new('RGBA', image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    tile_w = (inner_w - 2 * 20) / 3
    items = [
        (stats['partidos_jugados'], _('Partidos')),
        (stats['sets_disputados'], _('Sets jugados')),
        (stats['titularidades'], _('Titularidades')),
    ]
    for index, (value, label) in enumerate(items):
        x = _PAD_X + index * (tile_w + 20)
        draw.rounded_rectangle([x, y, x + tile_w, y + 196], radius=28, fill=_TILE)
    image.alpha_composite(overlay)
    draw = ImageDraw.Draw(image)
    for index, (value, label) in enumerate(items):
        x = _PAD_X + index * (tile_w + 20) + 24
        _text(draw, (x, y + 28), str(value), _font(_FONT_BOLD, 96), 'white')
        label, font = _fit_text(draw, label, font_path=_FONT_REGULAR, size=30, max_width=tile_w - 48, min_size=22)
        _text(draw, (x, y + 140), label, font, 'white')


def _draw_highlight(image, y, inner_w, highlight, primary):
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([_PAD_X, y, _PAD_X + inner_w, y + 216], radius=28, fill='white')
    disc = 104
    disc_x, disc_y = _PAD_X + 36, y + (216 - disc) // 2
    draw.ellipse([disc_x, disc_y, disc_x + disc, disc_y + disc], fill=primary)
    _draw_icon(draw, highlight['key'], disc_x + 24, disc_y + 24, 56, 'white')
    text_x = disc_x + disc + 28
    max_w = _PAD_X + inner_w - 36 - text_x
    caption, font = _fit_text(draw, highlight['caption'].upper(), font_path=_FONT_BOLD, size=26,
                              max_width=max_w, min_size=18)
    _text(draw, (text_x, y + 34), caption, font, _MUTED)
    title, font = _fit_text(draw, highlight['title'].upper(), font_path=_FONT_BOLD, size=68,
                            max_width=max_w, min_size=40)
    _text(draw, (text_x, y + 76), title, font, _INK)
    text, font = _fit_text(draw, highlight['text'], font_path=_FONT_REGULAR, size=32,
                           max_width=max_w, min_size=22)
    _text(draw, (text_x, y + 156), text, font, _INK)


def _draw_photo_box(image, box, person, role, photo):
    left, top, right, bottom = box
    border, radius = 14, 40
    size = (right - left - 2 * border, bottom - top - 2 * border)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(box, radius=radius, outline='white', width=border)

    inner = Image.new('RGBA', size, (0, 0, 0, 0))
    inner_draw = ImageDraw.Draw(inner)
    jersey = str(role.jersey_number) if role.jersey_number is not None else ''
    position = role.get_position_display() if role.position else ''
    if photo:
        with Image.open(BytesIO(photo)) as raw:
            inner.paste(_cover_crop(raw.convert('RGB'), *size), (0, 0))
        shade_h = min(420, size[1])
        shade = Image.new('RGBA', (size[0], shade_h), (0, 0, 0, 255))
        shade.putalpha(_vertical_alpha_gradient(size[0], shade_h, 0, 200))
        inner.alpha_composite(shade, (0, size[1] - shade_h))
        name_size, pill_text = 76, position
    else:
        # Sin foto, el dorsal gigante y tenue ocupa el hueco.
        if jersey:
            big = _font(_FONT_BOLD, 900)
            bbox = inner_draw.textbbox((0, 0), jersey, font=big)
            inner_draw.text((size[0] - bbox[2] + 40, -bbox[1] - 60), jersey, font=big, fill=(255, 255, 255, 36))
        name_size = 96
        pill_text = ' · '.join(filter(None, [position, _('nº %(n)s') % {'n': jersey} if jersey else '']))
        jersey = ''

    x = 48
    if jersey:
        dorsal_font = _font(_FONT_BOLD, 260)
        bbox = inner_draw.textbbox((0, 0), jersey, font=dorsal_font)
        inner_draw.text((x - bbox[0], size[1] - 40 - bbox[3]), jersey, font=dorsal_font, fill='white')
        x += bbox[2] - bbox[0] + 32
    max_w = size[0] - x - 48
    first, first_font = _fit_text(inner_draw, person.first_name.upper(), font_path=_FONT_BOLD,
                                  size=name_size, max_width=max_w, min_size=40)
    last, last_font = _fit_text(inner_draw, person.last_name.upper(), font_path=_FONT_BOLD,
                                size=name_size, max_width=max_w, min_size=40)
    line_h = round(name_size * 0.95)
    y = size[1] - 40 - 2 * line_h
    _text(inner_draw, (x, y), first, first_font, 'white')
    _text(inner_draw, (x, y + line_h), last, last_font, 'white')
    if pill_text:
        pill_font = _font(_FONT_BOLD, 30)
        pill_text = pill_text.upper()
        pill_w = inner_draw.textlength(pill_text, font=pill_font) + 44
        pill_y = y - 14 - 50
        inner_draw.rounded_rectangle([x, pill_y, x + pill_w, pill_y + 50], radius=25, fill='white')
        _text(inner_draw, (x + 22, pill_y + 11), pill_text, pill_font, _INK)

    inner.putalpha(Image.composite(inner.getchannel('A'), Image.new('L', size, 0), _rounded_mask(size, radius - border)))
    image.alpha_composite(inner, (left + border, top + border))
