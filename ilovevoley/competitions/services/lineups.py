"""Persistencia y agregados de las alineaciones de las actas federativas.

El JSON que devuelve ``parse_acta_lineup`` se guarda en ``Match.acta_data`` y
se desglosa en filas de ``MatchLineup`` (una por equipo + dorsal) para poder
calcular históricos por deportista sin volver a descargar el acta.
"""

import re

from django.db import transaction
from django.db.models import Count, Q, Sum
from unidecode import unidecode

from ilovevoley.rosters.models import PlayerRole

from ..models import Match, MatchLineup

_SET_POSITIONS = ('I', 'II', 'III', 'IV', 'V', 'VI')


def _words(value):
    return set(unidecode(value or '').upper().split())


def resolve_acta_team(name_acta, home_team, away_team):
    """Qué equipo del partido corresponde a un nombre de acta.

    Casa por solapamiento de palabras con los nombres reales; los empates
    (incluido un nombre vacío) recaen en el local.
    """
    name = _words(name_acta)
    home = _words(home_team.name if home_team else '')
    away = _words(away_team.name if away_team else '')
    return home_team if len(name & home) >= len(name & away) else away_team


def _roles_lookup(match):
    """{(team_id, jersey): PlayerRole} para resolver acta → Person.

    Se acota a la temporada de la liga cuando existe: un mismo dorsal cambia de
    dueño entre temporadas y sin ese filtro el histórico quedaría mal asignado.
    No se filtra por ``is_active``: un rol desactivado al acabar la temporada
    sigue siendo el dueño de ese dorsal en sus partidos.
    """
    teams = [t for t in (match.home_team, match.away_team) if t]
    if not teams:
        return {}
    roles = PlayerRole.objects.filter(team__in=teams, jersey_number__isnull=False)
    season = match.league.season if match.league_id else None
    if season is not None:
        roles = roles.filter(season=season)
    # Ante un dorsal repetido en la misma temporada, el rol activo gana; a
    # igualdad, el más reciente (id mayor) para que el orden sea determinista.
    roles = roles.order_by('is_active', 'id')
    return {
        (role.team_id, role.jersey_number): role
        for role in roles.select_related('person')
    }


def _bucket(stats, team, jersey, name=None):
    key = (team.id if team else None, jersey, name if jersey is None else '')
    if key not in stats:
        stats[key] = {
            'team': team,
            'jersey_number': jersey,
            'name_acta': name or '',
            'is_convocado': False,
            'sets_played': 0,
            'sets_started': 0,
        }
    return stats[key]


def build_match_lineups(match, lineup_data):
    """Convierte el dict del acta en instancias de ``MatchLineup`` sin guardar.

    Cuenta sets jugados (inicial o entrando como suplente) y sets como titular
    (posiciones I-VI) por dorsal y equipo.
    """
    home_team, away_team = match.home_team, match.away_team
    stats = {}

    for convocados, team in (
        (lineup_data.get('home_convocados') or [], home_team),
        (lineup_data.get('away_convocados') or [], away_team),
    ):
        for entry in convocados:
            matched = re.match(r'^(\d+)\s+(.+)$', (entry or '').strip())
            if matched:
                item = _bucket(stats, team, int(matched.group(1)))
                item['is_convocado'] = True
                item['name_acta'] = matched.group(2).strip()
            else:
                _bucket(stats, team, None, name=(entry or '').strip())

    for set_data in lineup_data.get('sets') or []:
        for team_data in set_data.get('teams') or []:
            team = resolve_acta_team(team_data.get('name'), home_team, away_team)
            for entry in team_data.get('lineup') or []:
                jersey = entry.get('number')
                if jersey is None:
                    continue
                item = _bucket(stats, team, jersey)
                item['sets_played'] += 1
                if entry.get('position') in _SET_POSITIONS:
                    item['sets_started'] += 1
                sub_number = (entry.get('sub') or {}).get('number')
                if sub_number is not None:
                    _bucket(stats, team, sub_number)['sets_played'] += 1

    roles = _roles_lookup(match)
    rows = []
    for item in stats.values():
        team = item['team']
        if team is None:
            continue
        role = roles.get((team.id, item['jersey_number'])) if item['jersey_number'] is not None else None
        rows.append(MatchLineup(
            match=match,
            team=team,
            person=role.person if role else None,
            jersey_number=item['jersey_number'],
            name_acta=item['name_acta'],
            is_convocado=item['is_convocado'],
            sets_played=item['sets_played'],
            sets_started=item['sets_started'],
        ))
    return rows


@transaction.atomic
def store_match_lineups(match, lineup_data):
    """Guarda el JSON del acta y reconstruye sus filas de alineación.

    Bloquea el partido para serializar dos peticiones simultáneas de la misma
    acta: sin el lock, el delete + bulk_create puede chocar con la constraint
    única por dorsal.
    """
    Match.all_objects.select_for_update().filter(pk=match.pk).first()
    match.acta_data = lineup_data
    update_fields = ['acta_data', 'updated_at']
    if not match.set_scores:
        from ilovevoley.competitions.services.sets import extract_set_scores
        from ilovevoley.videos.scraping.base import is_penalty_result

        scores = extract_set_scores(
            lineup_data,
            home_name=match.home_team_display,
            away_name=match.away_team_display,
        )
        if scores:
            match.set_scores = [list(score) for score in scores]
            update_fields.append('set_scores')
            if not match.result_penalized and is_penalty_result(match.set_scores):
                match.result_penalized = True
                update_fields.append('result_penalized')

    match.save(update_fields=update_fields)
    MatchLineup.objects.filter(match=match).delete()
    MatchLineup.objects.bulk_create(build_match_lineups(match, lineup_data))


def get_player_season_stats(person, season=None, teams=None):
    """Agregados de un deportista para una temporada (o todas si es ``None``).

    ``teams`` acota al ámbito del tenant para no mezclar equipos de otros clubes.
    """
    lineups = MatchLineup.objects.filter(person=person).exclude(match__status='withdrawn')
    if season is not None:
        lineups = lineups.filter(match__league__season=season)
    if teams is not None:
        lineups = lineups.filter(team__in=teams)

    totals = lineups.aggregate(
        convocatorias=Count('id', filter=Q(is_convocado=True)),
        partidos_jugados=Count('id', filter=Q(sets_played__gt=0)),
        titularidades=Count('id', filter=Q(sets_started__gt=0)),
        sets_disputados=Sum('sets_played'),
        sets_titular=Sum('sets_started'),
    )
    return {
        'convocatorias': totals['convocatorias'] or 0,
        'partidos_jugados': totals['partidos_jugados'] or 0,
        'titularidades': totals['titularidades'] or 0,
        'sets_disputados': totals['sets_disputados'] or 0,
        'sets_titular': totals['sets_titular'] or 0,
    }
