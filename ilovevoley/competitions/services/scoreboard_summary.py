"""Presentación del resumen que envía el marcador al cerrar el partido (#652)."""

from django.utils.translation import gettext as _
from django.utils.translation import ngettext

MAX_POINT = 99
MAX_SECONDS = 12 * 3600


def _bounded_int(value, maximum):
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 0 or value > maximum:
        return None
    return value


def format_duration(seconds):
    """Duración legible. None si no hay un entero positivo en rango.

    0 no es una duración: el marcador lo manda cuando el cronómetro no arrancó.
    """
    seconds = _bounded_int(seconds, MAX_SECONDS)
    if not seconds:
        return None
    hours, rem = divmod(seconds, 3600)
    minutes, _secs = divmod(rem, 60)
    if hours and minutes:
        return _('%(hours)s h %(minutes)s min') % {'hours': hours, 'minutes': minutes}
    if hours:
        return _('%(hours)s h') % {'hours': hours}
    if minutes:
        return _('%(minutes)s min') % {'minutes': minutes}
    return _('%(seconds)s s') % {'seconds': seconds}


def momentum_points(timeline):
    """Puntos válidos de la cronología: diferencia local − visitante frente al tiempo."""
    if not isinstance(timeline, list):
        return []
    points = []
    for raw in timeline:
        if not isinstance(raw, dict):
            continue
        home = _bounded_int(raw.get('home'), MAX_POINT)
        away = _bounded_int(raw.get('away'), MAX_POINT)
        instant = _bounded_int(raw.get('t'), MAX_SECONDS)
        if home is None or away is None or instant is None:
            continue
        points.append({'t': instant, 'diff': home - away})
    return points


def momentum_polyline(points):
    """Coordenadas SVG 0–100 × 0–40. El local por delante queda por encima del centro."""
    if len(points) < 2:
        return None
    start = min(point['t'] for point in points)
    span = max(point['t'] for point in points) - start or 1
    amplitude = max(max(abs(point['diff']) for point in points), 1)
    coords = []
    for point in points:
        x = (point['t'] - start) / span * 100
        y = 20 - (point['diff'] / amplitude) * 16
        coords.append(f'{x:.1f},{y:.1f}')
    return ' '.join(coords)


def caption_lines(summary):
    """Líneas cortas para la story: duración total y rachas local-visitante."""
    if not isinstance(summary, dict):
        return []
    lines = []
    duration = format_duration(summary.get('duration_seconds'))
    if duration:
        lines.append(_('Duración %(duration)s') % {'duration': duration})
    streaks = summary.get('max_streak')
    if isinstance(streaks, dict):
        home = _bounded_int(streaks.get('home'), MAX_POINT)
        away = _bounded_int(streaks.get('away'), MAX_POINT)
        if home is not None and away is not None:
            lines.append(_('Rachas %(home)s-%(away)s') % {'home': home, 'away': away})
    return lines


def display_payload(summary, *, home_name, away_name):
    """Estructura para la ficha. None si no hay nada que mostrar."""
    if not isinstance(summary, dict):
        return None
    streaks = summary.get('max_streak') if isinstance(summary.get('max_streak'), dict) else {}
    sets = []
    raw_sets = summary.get('sets')
    if isinstance(raw_sets, list):
        for raw in raw_sets:
            if not isinstance(raw, dict):
                continue
            number = _bounded_int(raw.get('set'), 9)
            if number is None:
                continue
            winner = raw.get('winner')
            if winner == 'home':
                winner_name = home_name
            elif winner == 'away':
                winner_name = away_name
            else:
                winner_name = ''
            comeback = _bounded_int(raw.get('max_comeback'), MAX_POINT)
            comeback_label = None
            if winner_name and comeback:
                comeback_label = ngettext(
                    '%(team)s remontó %(points)s punto',
                    '%(team)s remontó %(points)s puntos',
                    comeback,
                ) % {'team': winner_name, 'points': comeback}
            points = momentum_points(raw.get('timeline'))
            sets.append({
                'number': number,
                'duration_label': format_duration(raw.get('duration_seconds')),
                'comeback_label': comeback_label,
                'polyline': momentum_polyline(points),
                'diffs': [point['diff'] for point in points],
            })
    streak_home = _bounded_int(streaks.get('home'), MAX_POINT)
    streak_away = _bounded_int(streaks.get('away'), MAX_POINT)
    # La comparativa solo tiene sentido con los dos lados, igual que en la story.
    if streak_home is None or streak_away is None:
        streak_home = streak_away = None
    payload = {
        'duration_label': format_duration(summary.get('duration_seconds')),
        'streak_home': streak_home,
        'streak_away': streak_away,
        'sets': sets,
    }
    if (
        payload['duration_label'] is None
        and streak_home is None
        and streak_away is None
        and not sets
    ):
        return None
    return payload
