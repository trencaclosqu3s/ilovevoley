from functools import wraps

from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.translation import gettext as _

from ilovevoley.competitions.models import Standing
from ilovevoley.competitions.services.public_portal import (
    public_leagues,
    public_matches,
    public_standings_for_league,
)
from ilovevoley.core.models import Season
from ilovevoley.core.season_utils import resolve_season_filter

INDEX_LEAGUE_LIMIT = 12
DETAIL_MATCH_LIMIT = 30
LIST_MATCH_LIMIT = 200
UPCOMING_STATUSES = ('scheduled', 'in_progress')


def brand_portal_required(view_func):
    """El portal vive solo en el dominio raíz; en un tenant responde 404 (#124)."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if getattr(request, 'tenant', None) is not None:
            raise Http404()
        return view_func(request, *args, **kwargs)

    return wrapper


def _season_context(request):
    season, selected = resolve_season_filter(request)
    return {
        'season': season,
        'selected_season': selected,
        'seasons': Season.objects.order_by('-start_year'),
    }


@brand_portal_required
def index(request):
    ctx = _season_context(request)
    ctx['leagues'] = public_leagues(ctx['season'])[:INDEX_LEAGUE_LIMIT]
    ctx['title'] = _('Competición')
    return render(request, 'competitions/portal/index.html', ctx)


@brand_portal_required
def league_list(request):
    ctx = _season_context(request)
    ctx['leagues'] = public_leagues(ctx['season'])
    ctx['title'] = _('Ligas')
    return render(request, 'competitions/portal/league_list.html', ctx)


@brand_portal_required
def league_detail(request, league_id):
    # Acceso directo por URL: no depende de ?season=, la liga fija su temporada.
    league = get_object_or_404(public_leagues(None), pk=league_id)
    ctx = _season_context(request)
    ctx.update({'season': league.season, 'selected_season': str(league.season_id)})
    matches = public_matches(league.season).filter(league=league)
    ctx.update({
        'league': league,
        'standings': public_standings_for_league(league),
        'upcoming': matches.filter(
            status__in=UPCOMING_STATUSES, match_date__gte=timezone.now(),
        )[:DETAIL_MATCH_LIMIT],
        'recent': matches.filter(status='finished').order_by('-match_date')[:DETAIL_MATCH_LIMIT],
        'title': league.name,
    })
    return render(request, 'competitions/portal/league_detail.html', ctx)


def _filter_by_league(request, matches):
    league_id = request.GET.get('league')
    if league_id and league_id.isdigit():
        matches = matches.filter(league_id=league_id)
    return matches


@brand_portal_required
def calendar_view(request):
    ctx = _season_context(request)
    matches = public_matches(ctx['season']).filter(
        status__in=UPCOMING_STATUSES, match_date__gte=timezone.now(),
    )
    ctx.update({
        'matches': _filter_by_league(request, matches)[:LIST_MATCH_LIMIT],
        'leagues': public_leagues(ctx['season']),
        'selected_league_id': request.GET.get('league', ''),
        'title': _('Calendario'),
    })
    return render(request, 'competitions/portal/calendar.html', ctx)


@brand_portal_required
def results_view(request):
    ctx = _season_context(request)
    matches = public_matches(ctx['season']).filter(status='finished').order_by('-match_date')
    ctx.update({
        'matches': _filter_by_league(request, matches)[:LIST_MATCH_LIMIT],
        'leagues': public_leagues(ctx['season']),
        'selected_league_id': request.GET.get('league', ''),
        'title': _('Resultados'),
    })
    return render(request, 'competitions/portal/results.html', ctx)


@brand_portal_required
def standings_view(request):
    ctx = _season_context(request)
    leagues = public_leagues(ctx['season'])
    league_id = request.GET.get('league')
    selected_league = None
    standings = Standing.objects.none()
    if league_id:
        if not league_id.isdigit():
            raise Http404()
        selected_league = get_object_or_404(leagues, pk=league_id)
        standings = public_standings_for_league(selected_league)
    ctx.update({
        'leagues': leagues,
        'selected_league': selected_league,
        'standings': standings,
        'title': _('Clasificación'),
    })
    return render(request, 'competitions/portal/standings.html', ctx)
