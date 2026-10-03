"""Búsqueda pública de sedes por equipo, club, pabellón o municipio.

Devuelve dos tipos de coincidencias:

* **equipos** que participan en las ligas de la organización actual, con sus
  próximos partidos y la ubicación de cada uno (misma resolución que el feed
  iCal vía :func:`get_match_location_info`). Si un equipo no tiene partidos
  próximos se ofrece su sede habitual (``default_venue``).
* **pabellones** (``Venue``) encontrados directamente por nombre, nombre corto,
  alias o municipio, con su dirección, enlace a Maps y los próximos partidos que
  se disputan allí dentro de las ligas del tenant.
"""

from django.db.models import Q, Window
from django.db.models.functions import RowNumber
from django.utils import timezone

from ilovevoley.competitions.models import League, Match, Venue
from ilovevoley.competitions.services.venue_service import get_match_location_info
from ilovevoley.core.models import Season
from ilovevoley.teams.models import Team

MIN_QUERY_LENGTH = 3
MAX_TEAMS = 20
MAX_MATCHES_PER_TEAM = 5
MAX_VENUES = 20
MAX_MATCHES_PER_VENUE = 5


def _tenant_league_ids(tenant):
    """IDs de las ligas visibles del tenant en la temporada actual."""
    leagues = League.objects.for_tenant(tenant)
    season = Season.objects.current()
    if season is not None:
        leagues = leagues.filter(season=season)
    return list(leagues.values_list('pk', flat=True))


def _venue_payload(venue):
    if venue is None:
        return None
    return {
        'name': venue.name,
        'short_name': venue.short_name,
        'city': venue.city,
        'street': venue.address,
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


def _venue_match_payload(match, active_venues):
    """Partido ofrecido dentro de una tarjeta de sede (sin lado local/visitante)."""
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
        'location_text': info['location_text'],
        'maps_url': info['maps_url'],
    }


def search_team_locations(
    tenant, query, *, max_teams=MAX_TEAMS, max_matches=MAX_MATCHES_PER_TEAM,
    league_ids=None, active_venues=None,
):
    """Devuelve los equipos que casan con ``query`` y sus próximos partidos.

    El ámbito son las ligas visibles de la organización (``League.for_tenant``)
    de la temporada actual; la coincidencia es por nombre de equipo o de club.
    La respuesta es una lista de dicts lista para serializar a JSON o pintar en
    plantilla; nunca expone equipos de otras organizaciones.

    ``league_ids`` y ``active_venues`` permiten reutilizar los cálculos cuando
    se encadenan varios buscadores (ver :func:`search_locations`).
    """
    query = (query or '').strip()
    if tenant is None or len(query) < MIN_QUERY_LENGTH:
        return []

    if league_ids is None:
        league_ids = _tenant_league_ids(tenant)
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
    if active_venues is None:
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
            'type': 'team',
            'team_id': team.id,
            'team_name': team.display_name_with_variant,
            'category': team.category.name if team.category_id else None,
            'club_name': team.club.official_name if team.club_id else None,
            'matches': matches,
            'default_venue': default_venue,
        })
    return results


def search_venues(
    tenant, query, *, max_venues=MAX_VENUES, max_matches=MAX_MATCHES_PER_VENUE,
    league_ids=None, active_venues=None,
):
    """Devuelve los pabellones que casan con ``query`` por nombre, alias o municipio.

    El catálogo de ``Venue`` es global; la coincidencia se hace contra
    ``name``, ``short_name``, ``city`` y ``aliases``. Los partidos próximos que
    se muestran en cada tarjeta sí se acotan a las ligas del tenant, así que una
    sede puede aparecer aunque no tenga partidos en la organización activa.
    """
    query = (query or '').strip()
    if len(query) < MIN_QUERY_LENGTH:
        return []

    venues = list(
        Venue.objects.filter(is_active=True)
        .filter(
            Q(name__icontains=query)
            | Q(short_name__icontains=query)
            | Q(city__icontains=query)
            | Q(aliases__icontains=query),
        )
        .order_by('city', 'name')[:max_venues]
    )
    if not venues:
        return []

    if league_ids is None:
        league_ids = _tenant_league_ids(tenant) if tenant is not None else []
    if active_venues is None:
        active_venues = list(Venue.objects.filter(is_active=True))

    matches_by_venue = {}
    if league_ids:
        now = timezone.now()
        venue_ids = [venue.id for venue in venues]
        # ROW_NUMBER() por sede: limita a ``max_matches`` los partidos de cada
        # pabellón sin que una sede ruidosa consuma el cupo de las demás.
        ranked = (
            Match.objects.filter(
                venue_ref_id__in=venue_ids,
                league_id__in=league_ids,
                match_date__gte=now,
            )
            .annotate(
                row_number=Window(
                    expression=RowNumber(),
                    partition_by=['venue_ref_id'],
                    order_by='match_date',
                ),
            )
            .filter(row_number__lte=max_matches)
            .select_related('home_team', 'away_team', 'venue_ref')
            .order_by('match_date')
        )
        for match in ranked:
            matches_by_venue.setdefault(match.venue_ref_id, []).append(match)

    results = []
    for venue in venues:
        matches = [
            _venue_match_payload(match, active_venues)
            for match in matches_by_venue.get(venue.id, [])
        ]
        payload = _venue_payload(venue)
        payload.update({
            'type': 'venue',
            'venue_id': venue.id,
            'matches': matches,
        })
        results.append(payload)
    return results


def search_locations(tenant, query):
    """Buscador unificado: equipos del tenant primero, pabellones después."""
    query = (query or '').strip()
    if tenant is None or len(query) < MIN_QUERY_LENGTH:
        return []
    league_ids = _tenant_league_ids(tenant)
    active_venues = list(Venue.objects.filter(is_active=True))
    return (
        search_team_locations(
            tenant, query, league_ids=league_ids, active_venues=active_venues,
        )
        + search_venues(
            tenant, query, league_ids=league_ids, active_venues=active_venues,
        )
    )
