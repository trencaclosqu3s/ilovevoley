# ilovevoley/competitions/services/public_portal.py
from django.db.models import QuerySet

from ilovevoley.competitions.models import League, Match, Standing

PORTAL_VISIBILITY = ('main', 'historical')
SITEMAP_MATCH_LIMIT = 200


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
