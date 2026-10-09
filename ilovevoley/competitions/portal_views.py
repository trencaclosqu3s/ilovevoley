from functools import wraps

from django.http import Http404
from django.shortcuts import render
from django.utils.translation import gettext as _

from ilovevoley.competitions.services.public_portal import public_leagues
from ilovevoley.core.models import Season
from ilovevoley.core.season_utils import resolve_season_filter

INDEX_LEAGUE_LIMIT = 12


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
