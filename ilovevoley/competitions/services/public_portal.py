# ilovevoley/competitions/services/public_portal.py
import json

from django.db.models import QuerySet

from ilovevoley.competitions.models import League, Match, Standing

PORTAL_VISIBILITY = ('main', 'historical')
SITEMAP_MATCH_LIMIT = 200
SITEMAP_LEAGUE_LIMIT = 500


def public_leagues(season=None, *, include_friendly=False) -> QuerySet:
    qs = League.objects.filter(visibility_type__in=PORTAL_VISIBILITY)
    if season is not None:
        qs = qs.filter(season=season)
    if not include_friendly:
        qs = qs.exclude(competition_type='friendly')
    return qs.select_related('season').prefetch_related('categories').order_by('name')


def public_matches(season=None, *, include_friendly=False) -> QuerySet:
    qs = Match.objects.filter(
        league__in=public_leagues(season, include_friendly=include_friendly),
    ).select_related(
        'home_team', 'away_team', 'league', 'venue_ref',
    )
    return qs.order_by('match_date')


def public_standings_for_league(league) -> QuerySet:
    return (
        Standing.objects.filter(league=league)
        .select_related('team')
        .order_by('position')
    )


def sports_event_jsonld(match, absolute_url: str) -> dict:
    """SportsEvent schema.org del partido; nunca incluye jugadores ni acta."""
    home = match.home_team_display
    away = match.away_team_display
    location_name = match.venue_ref.name if match.venue_ref_id else match.venue
    data = {
        '@context': 'https://schema.org',
        '@type': 'SportsEvent',
        'name': f'{home} vs {away}',
        'url': absolute_url,
        'startDate': match.match_date.isoformat(),
        'homeTeam': {'@type': 'SportsTeam', 'name': home},
        'awayTeam': {'@type': 'SportsTeam', 'name': away},
    }
    if location_name:
        data['location'] = {'@type': 'Place', 'name': location_name}
    if match.status == 'finished' and match.home_score is not None and match.away_score is not None:
        data['description'] = f'{match.home_score}-{match.away_score}'
    return data


def sports_organization_jsonld(absolute_url: str) -> dict:
    """SportsOrganization de la marca para índice y listados; sin datos de personas."""
    return {
        '@context': 'https://schema.org',
        '@type': 'SportsOrganization',
        'name': 'I Love Voley',
        'sport': 'Volleyball',
        'url': absolute_url,
    }


def jsonld_script_payload(data: dict) -> str:
    """JSON listo para <script type="application/ld+json">; escapa "<" para no cerrar el script."""
    return json.dumps(data, ensure_ascii=False).replace('<', '\\u003c')


def portal_sitemap_paths() -> list[str]:
    """Paths relativos del portal para el sitemap; el host de marca lo pone quien llama."""
    from django.urls import reverse

    from ilovevoley.core.models import Season

    paths = [
        reverse('portal:index'),
        reverse('portal:league_list'),
        reverse('portal:calendar'),
        reverse('portal:results'),
        reverse('portal:standings'),
    ]
    season = Season.objects.current()
    league_ids = public_leagues(season).values_list('id', flat=True)[:SITEMAP_LEAGUE_LIMIT]
    for league_id in league_ids:
        paths.append(reverse('portal:league_detail', args=[league_id]))
    finished = public_matches(season).filter(status='finished').order_by('-match_date')
    for match_id in finished.values_list('id', flat=True)[:SITEMAP_MATCH_LIMIT]:
        paths.append(reverse('portal:match_detail', args=[match_id]))
    return paths
