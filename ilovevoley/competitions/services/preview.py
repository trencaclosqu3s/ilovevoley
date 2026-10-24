"""Previa de un partido pendiente: historial entre ambos equipos y cómo llegan.

Todo sale de ``Match`` y ``Standing`` ya scrapeados. El número de consultas es
fijo (historial, clasificación y forma de cada equipo), sin N+1.
"""

from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import gettext as _

from ilovevoley.competitions.models import Match, Standing
from ilovevoley.competitions.services.sets import match_set_scores

MAX_HEAD_TO_HEAD = 10
FORM_SIZE = 5


def _finished():
    return Match.objects.filter(
        status='finished', home_score__isnull=False, away_score__isnull=False,
    )


def _won(match, team_id):
    if match.home_team_id == team_id:
        return match.home_score > match.away_score
    return match.away_score > match.home_score


def _recent_matches(team_id, before):
    """Últimos partidos jugados del equipo, del más antiguo al más reciente."""
    matches = (
        _finished()
        .filter(Q(home_team_id=team_id) | Q(away_team_id=team_id), match_date__lt=before)
        .select_related('home_team', 'away_team')
        .order_by('-match_date')[:FORM_SIZE]
    )
    # Como se lee una racha.
    return list(reversed(matches))


def _form(team_id, before):
    return [_won(m, team_id) for m in _recent_matches(team_id, before)]


def _head_to_head_filter(match):
    """Enfrentamientos entre los dos equipos, también de temporadas anteriores.

    ``Team`` no sirve como identidad entre temporadas: la federación cambia su id
    cada año y el nombre cambia con los patrocinadores. La identidad estable es
    ``TeamIdentity`` (#428), así que el cruce principal es por el par de
    identidades. Los ids de club que trae cada partido de la federación son el
    respaldo para equipos aún sin identidad, dentro de la misma categoría (que ya
    fija el género). Si una identidad agrupa varios equipos (Groc/Lila), aparecen
    todos; cada fila muestra su nombre. Los partidos sin ids de club (RFEVB,
    amistosos) entran por el par de ``Team``.
    """
    home_id, away_id = match.home_team_id, match.away_team_id
    by_team = (
        Q(home_team_id=home_id, away_team_id=away_id)
        | Q(home_team_id=away_id, away_team_id=home_id)
    )
    home_identity, away_identity = match.home_team.identity_id, match.away_team.identity_id
    if home_identity and away_identity:
        by_team |= (
            Q(home_team__identity_id=home_identity, away_team__identity_id=away_identity)
            | Q(home_team__identity_id=away_identity, away_team__identity_id=home_identity)
        )
    if match.league_id:
        categories_pks = match.league.categories.values('pk')
        by_team = by_team & (
            Q(league_id=match.league_id)
            | Q(league__categories__in=categories_pks)
            | Q(league__isnull=True)
        )

    local, away = match.federation_club_local_id, match.federation_club_away_id
    # El parser guarda str(None) cuando la federación envía null: no es un club.
    if not (local and away and match.league_id) or {local, away} & {'None', '0'}:
        return by_team
    by_club = (
        Q(federation_club_local_id=local, federation_club_away_id=away)
        | Q(federation_club_local_id=away, federation_club_away_id=local)
    ) & Q(league__categories__in=match.league.categories.values('pk'))
    return by_team | by_club


def _head_to_head(match):
    head_to_head = list(
        _finished()
        .filter(_head_to_head_filter(match))
        .exclude(pk=match.pk)
        .select_related('home_team', 'away_team', 'league__season')
        .annotate(
            videos_count=Count('videos', distinct=True),
            images_count=Count('images', distinct=True),
        )
        .distinct()
        .order_by('-match_date')[:MAX_HEAD_TO_HEAD]
    )
    for past in head_to_head:
        past.preview_set_scores = match_set_scores(past)
    return head_to_head


def build_match_preview(match):
    """Datos de la previa, o ``None`` si no aplica o no hay nada que mostrar."""
    if match.is_finished or not match.home_team_id or not match.away_team_id:
        return None
    home_id, away_id = match.home_team_id, match.away_team_id

    head_to_head = _head_to_head(match)

    positions = {}
    if match.league_id:
        positions = dict(
            Standing.objects.filter(league_id=match.league_id, team_id__in=[home_id, away_id])
            .values_list('team_id', 'position')
        )

    home_form = _form(home_id, match.match_date)
    away_form = _form(away_id, match.match_date)

    if not (head_to_head or positions or home_form or away_form):
        return None
    return {
        'head_to_head': head_to_head,
        'home_position': positions.get(home_id),
        'away_position': positions.get(away_id),
        'home_form': home_form,
        'away_form': away_form,
    }


def preview_card_pills(match):
    """Pastillas de la story previa (#456): hora y posición de ambos en la clasificación.

    La hora 00:00 es la convención de "hora por confirmar" y no se muestra.
    """
    pills = []
    local = timezone.localtime(match.match_date)
    if (local.hour, local.minute) != (0, 0):
        pills.append(local.strftime('%H:%M'))
    if match.league_id:
        positions = dict(
            Standing.objects.filter(
                league_id=match.league_id, team_id__in=[match.home_team_id, match.away_team_id]
            ).values_list('team_id', 'position')
        )
        home, away = positions.get(match.home_team_id), positions.get(match.away_team_id)
        if home is not None and away is not None:
            pills.append(_('%(home)sº vs %(away)sº') % {'home': home, 'away': away})
    return pills


def _past_home_is_today_home(past, match):
    """Si el local del enfrentamiento pasado es el local de hoy; ``None`` si no se sabe.

    Misma identidad que ``_head_to_head_filter``: primero equipo e identidad entre
    temporadas; los ids de club de la federación, solo de respaldo y si los dos
    equipos de hoy no comparten club (derbi entre variantes del mismo club).
    """
    past_sides = (
        (past.home_team, past.federation_club_local_id, True),
        (past.away_team, past.federation_club_away_id, False),
    )
    today_sides = (
        (match.home_team, match.federation_club_local_id, True),
        (match.away_team, match.federation_club_away_id, False),
    )
    for past_team, _, is_past_home in past_sides:
        for today_team, _, today_is_home in today_sides:
            if past_team is None:
                continue
            if past_team.pk == today_team.pk or (
                past_team.identity_id and past_team.identity_id == today_team.identity_id
            ):
                return today_is_home == is_past_home

    if match.federation_club_local_id != match.federation_club_away_id:
        for _, past_fed, is_past_home in past_sides:
            if not past_fed or past_fed in ('None', '0'):
                continue
            for _, today_fed, today_is_home in today_sides:
                if past_fed == today_fed:
                    return today_is_home == is_past_home
    return None


def _standing_payload(standing):
    if standing is None:
        return None
    return {
        'position': standing.position,
        'points': standing.total_points,
        'played': standing.played,
    }


def _form_payload(team_id, before):
    return [
        {
            'result': 'W' if _won(m, team_id) else 'L',
            # Marcador de sets desde el punto de vista del equipo.
            'score': (
                f'{m.home_score}-{m.away_score}' if m.home_team_id == team_id
                else f'{m.away_score}-{m.home_score}'
            ),
            'opponent': (
                m.away_team_display if m.home_team_id == team_id else m.home_team_display
            ),
            'date': timezone.localtime(m.match_date).date().isoformat(),
        }
        for m in _recent_matches(team_id, before)
    ]


def build_overlay_preview(match):
    """Previa para el overlay del directo (#609): clasificación, forma y H2H.

    El ``winner`` del H2H es relativo al partido de hoy (``home``/``away`` de hoy),
    o ``None`` si el equipo pasado no se puede cruzar con ninguno de hoy.
    """
    standings = None
    if match.league_id:
        by_team = {
            s.team_id: s
            for s in Standing.objects.filter(
                league_id=match.league_id, team_id__in=[match.home_team_id, match.away_team_id]
            )
        }
        standings = {
            'home': _standing_payload(by_team.get(match.home_team_id)),
            'away': _standing_payload(by_team.get(match.away_team_id)),
        }
        if not (standings['home'] or standings['away']):
            standings = None

    meetings = []
    wins = {'home': 0, 'away': 0}
    for past in _head_to_head(match):
        past_home_won = past.home_score > past.away_score
        past_home_is_home = _past_home_is_today_home(past, match)
        winner = None
        if past_home_is_home is not None:
            winner = 'home' if past_home_won == past_home_is_home else 'away'
            wins[winner] += 1
        meetings.append({
            'date': timezone.localtime(past.match_date).date().isoformat(),
            'home': past.home_team_display,
            'away': past.away_team_display,
            'sets': f'{past.home_score}-{past.away_score}',
            'winner': winner,
        })

    return {
        'standings': standings,
        'form': {
            'home': _form_payload(match.home_team_id, match.match_date),
            'away': _form_payload(match.away_team_id, match.match_date),
        },
        'head_to_head': {
            'summary': {
                'home_wins': wins['home'], 'away_wins': wins['away'], 'total': len(meetings),
            },
            'matches': meetings,
        },
    }
