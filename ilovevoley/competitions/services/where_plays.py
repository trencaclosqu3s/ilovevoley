"""Búsqueda pública de sedes por equipo o club.

Resuelve, para los equipos que participan en las ligas de la organización actual,
sus próximos partidos y la ubicación de cada uno reutilizando
:func:`get_match_location_info` (la misma resolución que el feed iCal). Si un
equipo no tiene partidos próximos se ofrece su sede habitual (``default_venue``).
"""

from django.db.models import Q
from django.utils import timezone

from ilovevoley.competitions.models import League, Match, Venue
from ilovevoley.competitions.services.venue_service import get_match_location_info
from ilovevoley.core.models import Season
from ilovevoley.teams.models import Team

MIN_QUERY_LENGTH = 3
MAX_TEAMS = 20
MAX_MATCHES_PER_TEAM = 5


def _venue_payload(venue):
    if venue is None:
        return None
    return {
        'name': venue.name,
        'address': venue.full_address,
        'maps_url': venue.maps_url,
    }


def _match_payload(match, team, active_venues):
    info = get_match_location_info(match, active_venues=active_venues)
    local_dt = timezone.localtime(match.match_date)
    has_time = not (local_dt.hour == 0 and local_dt.minute == 0)
    return {
        'id': match.id,
        'date': local_dt.strftime('%d/%m/%Y'),
        'time': local_dt.strftime('%H:%M') if has_time else '',
        'has_time': has_time,
        'home_name': match.home_team_display,
        'away_name': match.away_team_display,
        'is_home': match.home_team_id == team.id,
        'location_text': info['location_text'],
        'maps_url': info['maps_url'],
    }


def search_team_locations(tenant, query, *, max_teams=MAX_TEAMS, max_matches=MAX_MATCHES_PER_TEAM):
    """Devuelve los equipos que casan con ``query`` y sus próximos partidos.

    El ámbito son las ligas visibles de la organización (``League.for_tenant``)
    de la temporada actual; la coincidencia es por nombre de equipo o de club.
    La respuesta es una lista de dicts lista para serializar a JSON o pintar en
    plantilla; nunca expone equipos de otras organizaciones.
    """
    query = (query or '').strip()
    if tenant is None or len(query) < MIN_QUERY_LENGTH:
        return []

    leagues = League.objects.for_tenant(tenant)
    season = Season.objects.current()
    if season is not None:
        leagues = leagues.filter(season=season)
    league_ids = list(leagues.values_list('pk', flat=True))
    if not league_ids:
        return []

    teams = (
        Team.objects.filter(
            Q(home_matches__league_id__in=league_ids)
            | Q(away_matches__league_id__in=league_ids),
            is_active=True,
        )
        .filter(Q(name__icontains=query) | Q(club__official_name__icontains=query))
        .select_related('club', 'club__default_venue', 'category')
        .distinct()
        .order_by('name')[:max_teams]
    )

    now = timezone.now()
    active_venues = list(Venue.objects.filter(is_active=True))
    results = []
    for team in teams:
        upcoming = list(
            Match.objects.filter(
                Q(home_team=team) | Q(away_team=team),
                league_id__in=league_ids,
                match_date__gte=now,
            )
            .select_related(
                'home_team', 'away_team', 'venue_ref',
                'home_team__club__default_venue',
            )
            .order_by('match_date')[:max_matches]
        )
        matches = [_match_payload(match, team, active_venues) for match in upcoming]
        default_venue = None
        if not matches and team.club_id:
            default_venue = _venue_payload(team.club.default_venue)
        results.append({
            'team_id': team.id,
            'team_name': team.display_name_with_variant,
            'category': team.category.name if team.category_id else None,
            'club_name': team.club.official_name if team.club_id else None,
            'matches': matches,
            'default_venue': default_venue,
        })
    return results
