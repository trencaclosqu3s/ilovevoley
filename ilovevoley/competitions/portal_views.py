import json
from functools import wraps

from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from ilovevoley.competitions.models import Standing
from ilovevoley.competitions.services.public_portal import (
    public_leagues,
    public_matches,
    public_standings_for_league,
    sports_event_jsonld,
)
from ilovevoley.core.models import Season
from ilovevoley.core.season_utils import resolve_season_filter
from ilovevoley.core.tenant_utils import build_absolute_url

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


def _render(request, template, ctx):
    # Canonical sin querystring: ?season=/?league= no generan URLs duplicadas.
    ctx['canonical_url'] = build_absolute_url(request.path, request=request)
    return render(request, template, ctx)


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
    return _render(request, 'competitions/portal/index.html', ctx)


@brand_portal_required
def league_list(request):
    ctx = _season_context(request)
    ctx['leagues'] = public_leagues(ctx['season'])
    ctx['title'] = _('Ligas')
    return _render(request, 'competitions/portal/league_list.html', ctx)


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
    return _render(request, 'competitions/portal/league_detail.html', ctx)


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
    return _render(request, 'competitions/portal/calendar.html', ctx)


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
    return _render(request, 'competitions/portal/results.html', ctx)


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
    return _render(request, 'competitions/portal/standings.html', ctx)


def _public_set_scores(match):
    """Parciales [[local, visitante], ...] solo si son enteros; descarta cualquier otra cosa."""
    sets = []
    for item in match.set_scores or []:
        if (
            isinstance(item, (list, tuple)) and len(item) == 2
            and all(isinstance(n, int) and not isinstance(n, bool) for n in item)
        ):
            sets.append((item[0], item[1]))
    return sets


@brand_portal_required
def match_detail(request, match_id):
    match = get_object_or_404(public_matches(None), pk=match_id)
    jsonld = sports_event_jsonld(
        match,
        build_absolute_url(reverse('portal:match_detail', args=[match.pk]), request=request),
    )
    # Solo datos federativos: sin vídeos, imágenes, stream, acta ni enlaces de compartir.
    return _render(request, 'competitions/portal/match_detail.html', {
        'match': match,
        'set_scores': _public_set_scores(match),
        'title': jsonld['name'],
        # Escapa "<" para que ningún nombre cierre el <script>.
        'jsonld_script': json.dumps(jsonld, ensure_ascii=False).replace('<', '\\u003c'),
    })
