import calendar
import hashlib
import json
import logging
import re as _re
from datetime import datetime, timedelta

import requests as http_requests
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.core.cache import cache
from django.core.validators import URLValidator
from django.db import transaction
from django.urls import reverse
from django.db.models import (
    BooleanField, Case, CharField, Count, Exists, IntegerField, OuterRef, Q, Subquery, Value, When,
)
from django.db.models.functions import Coalesce
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from ilovevoley.competitions.result_card import (
    CARD_STYLES,
    _file_field_bytes,
    render_result_card,
)
from ilovevoley.content.favorites import annotate_favorites, match_top_images
from ilovevoley.content.models import Image
from ilovevoley.core.mixins import get_club_team_filter, get_primary_club_team_name
from ilovevoley.core.models import Category, Season
from ilovevoley.core.protected_media import serve_protected_file
from ilovevoley.core.season_utils import resolve_season_filter
from ilovevoley.core.security import UnsafeURL, safe_get
from ilovevoley.core.tenancy import get_tenant_object_or_404
from ilovevoley.core.tenant_utils import (
    build_absolute_url,
    tenant_access_required,
    user_is_tenant_manager,
)
from ilovevoley.rosters.models import PlayerRole
from ilovevoley.teams.models import Team
from ilovevoley.videos.scraping import (
    league_max_sets,
    parse_acta_lineup,
    validate_volleyball_score,
)
from .forms import FriendlyMatchForm, MatchResultForm
from .models import League, Match, MatchChangeLog, MatchShareLink, Standing
from .services.lineups import resolve_acta_team, store_match_lineups
from .services.notifications import notify_match_live_stream, notify_match_result
from .services.preview import build_match_preview

from .services.sets import extract_set_scores, match_set_scores
from .services.where_plays import MIN_QUERY_LENGTH, search_locations
from .share import (
    ALLOWED_HOURS,
    create_match_share_link,
    default_hours,
    get_match_set_labels,
    group_match_media,
    resolve_match_share_link,
    revoke_match_share_link,
)

logger = logging.getLogger(__name__)


def _acta_lineup_cache_key(acta_url: str) -> str:
    """Clave corta y segura para backends con límite (p. ej. Memcached)."""
    digest = hashlib.md5(acta_url.encode(), usedforsecurity=False).hexdigest()
    return f'acta_lineup:{digest}'


def build_calendar_matches_payload(matches, club_team_name):
    """Serializa partidos del calendario para json_script (evita DOM-XSS vía escapejs+innerHTML)."""
    payload = []
    for match in matches:
        local_dt = timezone.localtime(match.match_date)
        time_str = local_dt.strftime('%H:%M')
        categories = ''
        if match.league_id:
            categories = ', '.join(c.name for c in match.league.categories.all())
        home_logo = ''
        away_logo = ''
        if match.home_team_id and match.home_team.display_logo:
            home_logo = match.home_team.display_logo
        if match.away_team_id and match.away_team.display_logo:
            away_logo = match.away_team.display_logo
        payload.append({
            'id': match.id,
            'day': local_dt.day,
            'date': local_dt.strftime('%d/%m/%Y'),
            'time': _('Sin horario confirmado') if time_str == '00:00' else time_str,
            'home_team': match.home_team_display,
            'away_team': match.away_team_display,
            'home_team_logo': home_logo,
            'away_team_logo': away_logo,
            'league': match.league.name if match.league_id else '',
            'category': categories,
            'venue': match.venue or '',
            'city': match.city or '',
            'result': match.result_display if match.is_finished else '',
            'videos_count': match.videos_count,
            'round_number': match.round_number,
            'is_friendly': match.is_friendly,
            'club_team_name': club_team_name or '',
        })
    return {'matches': payload}


@tenant_access_required()
def league_list(request):
    """Vista para mostrar todas las ligas disponibles"""
    leagues = (
        League.objects.for_tenant(request.tenant)
        .select_related('season')
        .prefetch_related('categories')
    )
    categories = Category.objects.filter(is_active=True).order_by('name')

    # Variable para controlar si mostrar todo el contenido
    show_all = request.GET.get('show_all', '0') == '1'
    category_filter = request.GET.get('category')
    show_friendly = request.GET.get('show_friendly', '0') == '1'  # Filtro para partidos amistosos
    show_past = request.GET.get('show_past', '0') == '1'  # Filtro para ligas pasadas

    # Aplicar filtro de categoría específica
    if category_filter:
        leagues = leagues.filter(categories__id=category_filter).distinct()
    # Filtrar por categorías preferidas del usuario si no se especifica otra cosa
    elif not show_all and request.user.has_preferred_categories(request.tenant):
        user_categories = request.user.preferred_categories_for(request.tenant)
        leagues = leagues.filter(categories__in=user_categories).distinct()

    # Filtrar partidos amistosos si no se quiere mostrar
    if not show_friendly:
        # Excluir ligas de partidos amistosos
        leagues = leagues.exclude(competition_type='friendly')

    now = timezone.now()
    has_pending_subquery = Exists(
        Match.objects.filter(
            league=OuterRef('pk'),
            status__in=['scheduled', 'in_progress'],
            match_date__gte=now,
        )
    )

    # Filtrar ligas pasadas si no se quiere mostrar
    if not show_past:
        leagues = leagues.filter(has_pending_subquery)

    matches_count_subquery = Coalesce(
        Subquery(
            Match.objects.filter(league=OuterRef('pk'))
            .values('league')
            .annotate(c=Count('*'))
            .values('c'),
            output_field=IntegerField(),
        ),
        0,
    )

    standings_count_subquery = Coalesce(
        Subquery(
            Standing.objects.filter(league=OuterRef('pk'))
            .values('league')
            .annotate(c=Count('*'))
            .values('c'),
            output_field=IntegerField(),
        ),
        0,
    )

    # Ordenar: ligas oficiales primero, luego amistosas, y por nombre dentro de cada tipo
    leagues = leagues.annotate(
        has_pending_matches_annotated=has_pending_subquery,
        matches_count=matches_count_subquery,
        standings_count=standings_count_subquery,
        sort_priority=Case(
            When(competition_type='friendly', then=Value(2)),
            default=Value(1),
            output_field=CharField(),
        )
    ).order_by('sort_priority', 'name')

    leagues_list = list(leagues)
    league_ids = [l.id for l in leagues_list]
    if league_ids:
        club_q = get_club_team_filter(request.tenant)
        matches_qs = Match.objects.filter(
            league_id__in=league_ids,
            status='scheduled',
        ).filter(club_q)
        if not show_friendly:
            matches_qs = matches_qs.filter(is_friendly=False)

        upcoming_matches = (
            matches_qs
            .select_related('home_team', 'away_team')
            .order_by('match_date')
        )
        next_official = {}
        next_friendly = {}
        for match in upcoming_matches:
            target = next_friendly if match.is_friendly else next_official
            target.setdefault(match.league_id, match)

        for league in leagues_list:
            league.next_official_match = next_official.get(league.id)
            league.next_friendly_match = next_friendly.get(league.id)

    return render(request, 'competitions/league_list.html', {
        'leagues': leagues_list,
        'categories': categories,
        'selected_category': category_filter,
        'show_all': show_all,
        'show_friendly': show_friendly,
        'show_past': show_past,
        'has_preferences': request.user.has_preferred_categories(request.tenant),
    })


@tenant_access_required()
def league_detail(request, league_id):
    """Vista detallada de una liga con partidos y clasificación"""
    league = get_tenant_object_or_404(
        League.objects, request.tenant, user=request.user, id=league_id, is_active=True
    )

    # NUEVO: Lógica de filtrado por fases
    show_all_phases = request.GET.get('all_phases', '1') == '1'
    selected_phase = request.GET.get('phase')

    # Obtener todas las fases si la liga es parte de un sistema de fases
    all_phases = league.get_all_phases(include_self=True) if (league.is_phase or league.phases.exists()) else [league]

    # Determinar qué partidos mostrar
    if show_all_phases and not selected_phase:
        # Mostrar todas las fases combinadas
        league_ids = [p.id for p in all_phases]
        matches = Match.objects.filter(league_id__in=league_ids)
        display_league = league.root_league
    elif selected_phase:
        # Mostrar fase específica (solo si pertenece al tenant)
        phase_league = None
        try:
            phase_league = League.objects.for_tenant(request.tenant).filter(
                id=selected_phase, is_active=True
            ).first()
        except (TypeError, ValueError):
            phase_league = None
        if phase_league is not None:
            matches = Match.objects.filter(league=phase_league)
            display_league = phase_league
        else:
            matches = Match.objects.filter(league=league)
            display_league = league
    else:
        # Mostrar solo esta liga
        matches = Match.objects.filter(league=league)
        display_league = league

    # Aplicar select_related
    matches = matches.select_related('home_team', 'away_team', 'league').order_by('-match_date')

    # Obtener clasificación (solo de la liga específica o root)
    standings = display_league.standings.select_related('team').order_by('position')

    # Filtros opcionales existentes
    round_filter = request.GET.get('round')
    if round_filter:
        matches = matches.filter(round_number=round_filter)

    with_videos = request.GET.get('with_videos')
    if bool(with_videos):
        matches = matches.filter(videos__isnull=False).distinct()

    available_rounds = matches.values_list('round_number', flat=True).distinct().order_by('round_number')

    # Total de vídeos de la liga: una sola consulta agregada, sin cargar los vídeos
    total_videos = matches.aggregate(total=Count('videos', distinct=True))['total'] or 0

    # Indicador de vídeos por partido sin prefetch: anotación distinct=True (ver #108)
    matches = matches.annotate(videos_count=Count('videos', distinct=True))

    # Paginación
    paginator = Paginator(matches, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'competitions/league_detail.html', {
        'league': display_league,
        'root_league': league.root_league,
        'all_phases': all_phases,
        'show_all_phases': show_all_phases,
        'selected_phase': selected_phase,
        'page_obj': page_obj,
        'total_videos': total_videos,
        'standings': standings,
        'available_rounds': available_rounds,
        'selected_round': round_filter,
        'with_videos': with_videos
    })


@tenant_access_required()
def match_detail(request, match_id):
    """Vista detallada de un partido con sus videos e imágenes"""
    match = get_object_or_404(
        Match.objects.select_related('home_team', 'away_team', 'league'),
        id=match_id,
    )

    is_own_match = Match.objects.filter(id=match.id).filter(
        get_club_team_filter(request.tenant)
    ).exists()

    if is_own_match:
        # Obtener videos del partido filtrados por tenant
        videos = match.videos.select_related('created_by', 'category').filter(organization=request.tenant)
        # Obtener imágenes aprobadas del partido filtradas por tenant
        images = annotate_favorites(
            match.images.filter(
                status='approved', organization=request.tenant
            ).select_related('uploaded_by'),
            request.user,
        )
        top_images = match_top_images(match, request.tenant, user=request.user, limit=3)
        can_manage = user_is_tenant_manager(request.user, request.tenant)
        stream_url = match.stream_url
    else:
        videos = match.videos.none()
        images = match.images.none()
        top_images = []
        can_manage = False
        stream_url = ''

    # Enlaces de compartición (solo relevantes para managers)
    share_links = []
    if can_manage:
        for link in match.share_links.filter(organization=request.tenant):
            share_links.append({
                'link': link,
                'url': build_absolute_url(
                    f'p/partido/{link.token}/', tenant=request.tenant, request=request
                ),
            })

    return render(request, 'competitions/match_detail.html', {
        'match': match,
        'videos': videos,
        'images': images,
        'top_images': top_images,
        'default_card_photo_id': top_images[0].id if top_images else None,
        'today': timezone.now().date(),
        'is_own_match': is_own_match,
        'can_manage_videos': can_manage,
        'can_edit_result': can_manage,
        'can_edit_stream': can_manage,
        'stream_url': stream_url,
        'is_live': match.is_live if is_own_match else False,
        'is_live_window': match.is_live_window if is_own_match else False,
        'share_links': share_links,
        'share_hours_choices': ALLOWED_HOURS,
        'share_default_hours': default_hours(),
        'set_scores': match_set_scores(match),
        'max_sets': league_max_sets(match.league) if match.league else 5,
        'preview': build_match_preview(match),
    })


def _load_set_scores_for_card(match):
    """Devuelve los parciales del partido para la tarjeta.

    Prioriza el JSON del acta ya persistido (o ``set_scores``, que cubre el
    scraping de resultados y la entrada manual). Solo descarga y parsea el HTML
    como fallback para actas antiguas sin ``acta_data`` guardado.
    """
    acta_url = match.official_acta_url or match.acta_html
    if match.acta_data is not None or not acta_url:
        return match_set_scores(match)

    cache_key = _acta_lineup_cache_key(acta_url)
    try:
        lineup_data = cache.get(cache_key)
        if lineup_data is None:
            acta_content = safe_get(
                acta_url,
                allowed_hosts=settings.ACTA_ALLOWED_HOSTS,
            )
            lineup_data = parse_acta_lineup(acta_content)
            cache.set(cache_key, lineup_data, 60 * 60 * 24)

        scores = extract_set_scores(
            lineup_data,
            home_name=match.home_team_display,
            away_name=match.away_team_display,
        )
        if scores:
            return scores
    except Exception as exc:
        logger.warning(
            'Acta no disponible para tarjeta del partido %s: %s',
            match.id,
            exc,
        )
    return match_set_scores(match)


@tenant_access_required()
def match_result_card(request, match_id):
    """Genera un PNG de resultado cuadrado o vertical para compartir."""
    try:
        match = get_tenant_object_or_404(
            Match.objects.select_related(
                'home_team',
                'home_team__club',
                'away_team',
                'away_team__club',
                'league',
            ),
            request.tenant,
            user=request.user,
            id=match_id,
        )
    except Http404:
        return JsonResponse({'error': _('Partido no encontrado')}, status=404)

    card_format = request.GET.get('format', 'square')
    if card_format not in ('square', 'story'):
        return JsonResponse({'error': _('Formato de tarjeta no válido')}, status=400)
    card_style = request.GET.get('style', 'completa')
    if card_style not in CARD_STYLES:
        return JsonResponse({'error': _('Estilo de tarjeta no válido')}, status=400)
    if (
        match.status != 'finished'
        or match.home_score is None
        or match.away_score is None
    ):
        return JsonResponse(
            {'error': _('No se puede compartir un partido sin resultado finalizado')},
            status=400,
        )

    photo_bytes = None
    if card_style == 'marco':
        photo_id = request.GET.get('photo_id', '')
        photo = None
        if photo_id.isdecimal():
            photo = match.images.filter(
                status='approved', organization=request.tenant, id=photo_id
            ).first()
        if not photo:
            return JsonResponse(
                {'error': _('Selecciona una foto del partido para el estilo "marco"')},
                status=400,
            )
        photo_bytes = _file_field_bytes(photo.thumbnail_large or photo.image)
        if photo_bytes is None:
            return JsonResponse(
                {'error': _('No se pudo leer la foto seleccionada')}, status=400
            )

    png = render_result_card(
        match=match,
        organization=request.tenant,
        card_format=card_format,
        card_style=card_style,
        photo=photo_bytes,
        sets=_load_set_scores_for_card(match),
    )
    response = HttpResponse(png, content_type='image/png')
    response['Content-Disposition'] = (
        f'attachment; filename="resultado-{match.id}-{card_format}.png"'
    )
    return response


@tenant_access_required()
def calendar_view(request):
    """Vista del calendario de partidos"""
    # Obtener filtros
    show_all_teams = request.GET.get('all_teams', '0') == '1'
    show_all = request.GET.get('show_all', '0') == '1'
    league_filter = request.GET.get('league')
    category_filter = request.GET.get('category')

    # Consulta base de partidos (withdrawn excluidos automáticamente por el manager)
    # distinct=True: los filtros por categoría hacen JOIN M2M y duplicarían el conteo
    matches = Match.objects.select_related(
        'home_team__club', 'away_team__club', 'league'
    ).prefetch_related('league__categories').annotate(
        videos_count=Count('videos', distinct=True)
    ).order_by('match_date')

    # Filtrar por equipo del club por defecto
    if not show_all_teams:
        matches = matches.filter(get_club_team_filter(request.tenant))
        matches = matches.annotate(is_own=Value(True, output_field=BooleanField()))
    else:
        matches = matches.annotate(
            is_own=Case(
                When(get_club_team_filter(request.tenant), then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
        )

    # Aplicar filtro de liga
    if league_filter:
        matches = matches.filter(league_id=league_filter)

    # Aplicar filtro de categoría
    if category_filter:
        matches = matches.filter(league__categories__id=category_filter).distinct()
    # Si no hay filtro de categoría, aplicar preferencias del usuario
    elif not show_all and request.user.has_preferred_categories(request.tenant):
        user_categories = request.user.preferred_categories_for(request.tenant)
        matches = matches.filter(league__categories__in=user_categories).distinct()

    # Obtener datos para filtros
    leagues = League.objects.for_tenant(request.tenant).order_by('name')
    categories = Category.objects.filter(is_active=True).order_by('name')

    # Obtener el mes actual o el solicitado
    try:
        year = int(request.GET.get('year', timezone.now().year))
        month = int(request.GET.get('month', timezone.now().month))
        start_date = timezone.make_aware(datetime(year, month, 1))
        if month == 12:
            next_month_start = timezone.make_aware(datetime(year + 1, 1, 1))
        else:
            next_month_start = timezone.make_aware(datetime(year, month + 1, 1))
        prev_month = start_date - timedelta(days=1)
    except (ValueError, TypeError, OverflowError):
        messages.warning(request, _('La fecha solicitada no es válida. Mostrando el mes actual.'))
        return redirect('competitions:calendar_view')

    monthly_matches = matches.filter(
        match_date__gte=start_date,
        match_date__lt=next_month_start,
    )


    # Navegación de meses
    next_month = next_month_start

    # Generar grid del calendario
    cal = calendar.Calendar(firstweekday=0)  # Lunes como primer día
    month_days = cal.monthdayscalendar(year, month)

    # Crear diccionario de partidos por día
    matches_by_day = {}
    for match in monthly_matches:
        day = match.match_date.day
        if day not in matches_by_day:
            matches_by_day[day] = []
        matches_by_day[day].append(match)

    # Crear estructura del calendario con partidos
    calendar_weeks = []
    for week in month_days:
        calendar_week = []
        for day in week:
            if day == 0:
                calendar_week.append({
                    'day': None,
                    'is_current_month': False,
                    'matches': []
                })
            else:
                day_matches = matches_by_day.get(day, [])
                is_today = (datetime.now().date() == datetime(year, month, day).date())
                calendar_week.append({
                    'day': day,
                    'is_current_month': True,
                    'is_today': is_today,
                    'matches': day_matches,
                    'match_count': len(day_matches)
                })
        calendar_weeks.append(calendar_week)

    # Obtener modo de vista (lista o calendario)
    view_mode = request.GET.get('view', 'list')  # 'list' o 'calendar'

    # Nombres de meses en español
    month_names_es = {
        1: _('Enero'), 2: _('Febrero'), 3: _('Marzo'), 4: _('Abril'),
        5: _('Mayo'), 6: _('Junio'), 7: _('Julio'), 8: _('Agosto'),
        9: _('Septiembre'), 10: _('Octubre'), 11: _('Noviembre'), 12: _('Diciembre')
    }

    club_team_name = get_primary_club_team_name(request.tenant)

    return render(request, 'competitions/calendar.html', {
        'matches': monthly_matches,
        'matches_json': build_calendar_matches_payload(monthly_matches, club_team_name),
        'club_team_name': club_team_name,
        'leagues': leagues,
        'categories': categories,
        'selected_league': league_filter,
        'selected_category': category_filter,
        'show_all_teams': show_all_teams,
        'show_all': show_all,
        'current_month': start_date,
        'prev_month': prev_month,
        'next_month': next_month,
        'year': year,
        'month': month,
        'calendar_weeks': calendar_weeks,
        'view_mode': view_mode,
        'month_name': month_names_es[month],
        'has_preferences': request.user.has_preferred_categories(request.tenant),
        'today': timezone.now().date(),
    })


RESULTS_PERIODS = ('recent', 'month', 'season')
RESULTS_RECENT_LIMIT = 20
RESULTS_PAGE_SIZE = 50


@tenant_access_required()
def results_view(request):
    """Listado de resultados ya jugados, complementario al calendario.

    Por defecto: equipos del club y categorías preferidas del usuario. Elegir
    equipos, ``all_teams`` o una categoría levanta esas restricciones para poder
    consultar cualquier equipo de cualquier categoría.
    """
    period = request.GET.get('period')
    if period not in RESULTS_PERIODS:
        period = 'recent'
    show_all_teams = request.GET.get('all_teams', '0') == '1'
    category_filter = request.GET.get('category', '')
    if not (category_filter.isascii() and category_filter.isdigit()):
        category_filter = ''
    team_ids = [int(t) for t in request.GET.getlist('teams') if t.isascii() and t.isdigit()]
    season, selected_season = resolve_season_filter(request)

    matches = Match.objects.select_related(
        'home_team__club', 'away_team__club', 'league'
    ).filter(status='finished', home_score__isnull=False, away_score__isnull=False)
    if season:
        matches = matches.filter(league__season=season)

    if team_ids:
        matches = matches.filter(Q(home_team_id__in=team_ids) | Q(away_team_id__in=team_ids))
    elif not show_all_teams:
        matches = matches.filter(get_club_team_filter(request.tenant))

    if category_filter:
        matches = matches.filter(league__categories__id=category_filter).distinct()
    elif not (team_ids or show_all_teams) and request.user.has_preferred_categories(request.tenant):
        matches = matches.filter(
            league__categories__in=request.user.preferred_categories_for(request.tenant)
        ).distinct()

    matches = matches.order_by('-match_date')
    if period == 'month':
        matches = matches.filter(match_date__gte=timezone.now() - timedelta(days=30))
    elif period == 'recent':
        matches = matches[:RESULTS_RECENT_LIMIT]

    page_obj = Paginator(matches, RESULTS_PAGE_SIZE).get_page(request.GET.get('page'))
    for match in page_obj:
        match.set_scores = match_set_scores(match)

    params = request.GET.copy()
    params.pop('page', None)

    return render(request, 'competitions/results.html', {
        'matches': page_obj,
        'page_obj': page_obj,
        'querystring': params.urlencode(),
        'period': period,
        'seasons': Season.objects.order_by('-start_year'),
        'selected_season': selected_season,
        'categories': Category.objects.filter(is_active=True).order_by('name'),
        'selected_category': category_filter,
        'show_all_teams': show_all_teams,
        'selected_teams': Team.objects.filter(pk__in=team_ids).order_by('name'),
    })


@tenant_access_required(api=True)
def ajax_results_teams(request):
    """Autocompletado del filtro de resultados: equipos de cualquier club."""
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'teams': []})
    teams = Team.objects.filter(name__icontains=query).select_related('category').order_by('name')[:10]
    return JsonResponse({'teams': [
        {'id': t.id, 'name': t.name, 'category': t.category.name if t.category else None}
        for t in teams
    ]})


@tenant_access_required(manager=True)
def friendly_match_create(request):
    """Vista para crear un partido amistoso"""
    if request.method == 'POST':
        logger.debug(f"POST data received: {request.POST}")

        form = FriendlyMatchForm(request.POST)
        if form.is_valid():
            match = form.save()
            messages.success(
                request,
                _('Partido amistoso creado: %(home)s vs %(away)s') % {
                    'home': match.home_team_display,
                    'away': match.away_team_display,
                }
            )
            return redirect('competitions:calendar_view')
        else:
            logger.error(f"Form errors: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    if field == '__all__':
                        messages.error(request, f'{error}')
                    else:
                        messages.error(request, f'{field}: {error}')
    else:
        form = FriendlyMatchForm()

    return render(request, 'competitions/friendly_match_form.html', {
        'form': form,
    })


@tenant_access_required(manager=True)
def ajax_search_teams(request):
    """Vista AJAX para buscar equipos con autocompletado inteligente.

    Por defecto acota los resultados al club/organización del tenant actual
    (``Team.objects.for_tenant``): un manager de otro club no debe ver equipos
    ajenos. Con ``scope=rival`` se busca explícitamente fuera del tenant para
    vincular rivales ya presentes en actas, devolviendo solo ``id`` y ``name``
    (sin club ni categoría).
    """
    query = request.GET.get('q', '').strip()
    category_id = request.GET.get('category_id', '').strip()
    scope = request.GET.get('scope', 'tenant').strip().lower()

    if len(query) < 2:
        return JsonResponse({'teams': []})

    # Buscar equipos existentes
    teams_query = Team.objects.filter(name__icontains=query)

    # Filtrar por categoría si se especifica
    if category_id:
        try:
            category = Category.objects.get(id=category_id)
            teams_query = teams_query.filter(category=category)
        except Category.DoesNotExist:
            pass

    # Modo rival explícito: equipos fuera del tenant, solo id y nombre.
    if scope == 'rival':
        tenant_team_ids = Team.objects.for_tenant(request.tenant).values('pk')
        rival_teams = teams_query.exclude(pk__in=tenant_team_ids).order_by('name')[:10]
        return JsonResponse({
            'teams': [{'id': team.id, 'name': team.name} for team in rival_teams]
        })

    # Por defecto, solo equipos del club/organización del tenant.
    teams = (
        teams_query.select_related('category', 'club')
        .for_tenant(request.tenant)
        .order_by('name')[:10]
    )

    # Formatear respuesta
    teams_data = []
    for team in teams:
        display_name = team.name
        if team.category:
            display_name += f" ({team.category.name})"
        if team.club:
            display_name += f" - {team.club.official_name}"

        teams_data.append({
            'id': team.id,
            'name': team.name,
            'display': display_name,
            'category': team.category.name if team.category else None,
        })

    return JsonResponse({'teams': teams_data})


@require_POST
@tenant_access_required(manager=True)
def ajax_add_match_result(request, match_id):
    """Vista AJAX para agregar resultado de partido"""
    try:
        match = Match.objects.for_tenant(request.tenant).select_related('league').get(id=match_id)
    except Match.DoesNotExist:
        return JsonResponse({'success': False, 'error': _('Partido no encontrado')}, status=404)

    # Verificar que el partido no tenga resultado ya
    if match.is_finished and match.home_score is not None and match.away_score is not None:
        return JsonResponse({'success': False, 'error': _('Este partido ya tiene resultado')}, status=400)

    # Verificar que el partido ya haya pasado o sea hoy
    if match.match_date.date() > timezone.now().date():
        return JsonResponse({'success': False, 'error': _('No se puede agregar resultado a un partido futuro')}, status=400)

    # Parsear datos JSON
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': _('Datos inválidos')}, status=400)

    # Crear formulario con los datos
    form = MatchResultForm(data, instance=match)

    if form.is_valid():
        home_score = form.cleaned_data['home_score']
        away_score = form.cleaned_data['away_score']
        if match.league and not validate_volleyball_score(home_score, away_score, match.league):
            return JsonResponse({
                'success': False,
                'error': _('Marcador inválido para el formato de la liga.'),
            }, status=400)
        try:
            match = form.save()
        except Exception:
            logger.exception("Error al guardar resultado del partido %s", match_id)
            return JsonResponse({
                'success': False,
                'error': _('Error interno al guardar el resultado.'),
            }, status=500)

        # El resultado ya está persistido: un fallo del aviso (p. ej. Redis caído)
        # no debe devolver error al cliente por algo que sí se guardó.
        try:
            notify_match_result(match, tenant=request.tenant)
        except Exception:
            logger.exception("Error al notificar el resultado del partido %s", match_id)

        return JsonResponse({
            'success': True,
            'message': _('Resultado guardado: %(result)s') % {'result': match.result_display},
            'result_display': match.result_display,
            'home_score': match.home_score,
            'away_score': match.away_score
        })
    else:
        # Recopilar errores del formulario
        errors = {}
        for field, field_errors in form.errors.items():
            errors[field] = field_errors[0] if field_errors else _('Error desconocido')

        return JsonResponse({
            'success': False,
            'error': _('Datos inválidos'),
            'errors': errors
        }, status=400)


@require_POST
@tenant_access_required(manager=True)
def ajax_edit_match_result(request, match_id):
    """Edita los parciales/resultado de un partido ya finalizado.

    Solo para partidos sin acta oficial: cuando hay acta, los parciales se toman
    de ella (documento federativo).
    """
    try:
        match = Match.objects.for_tenant(request.tenant).select_related('league').get(id=match_id)
    except Match.DoesNotExist:
        return JsonResponse({'success': False, 'error': _('Partido no encontrado')}, status=404)

    if match.acta_html or match.acta_data:
        return JsonResponse({
            'success': False,
            'error': _('Este partido tiene acta oficial; los parciales se toman del acta.'),
        }, status=400)

    if not match.is_finished:
        return JsonResponse({
            'success': False,
            'error': _('El partido todavía no tiene resultado.'),
        }, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': _('Datos inválidos')}, status=400)

    form = MatchResultForm(data, instance=match)
    if not form.is_valid():
        errors = {field: field_errors[0] for field, field_errors in form.errors.items() if field_errors}
        return JsonResponse({
            'success': False,
            'error': _('Datos inválidos'),
            'errors': errors,
        }, status=400)

    try:
        match = form.save()
    except Exception:
        logger.exception("Error al editar resultado del partido %s", match_id)
        return JsonResponse({
            'success': False,
            'error': _('Error interno al guardar el resultado.'),
        }, status=500)

    return JsonResponse({
        'success': True,
        'message': _('Resultado actualizado: %(result)s') % {'result': match.result_display},
        'result_display': match.result_display,
        'home_score': match.home_score,
        'away_score': match.away_score,
        'set_scores': match.set_scores,
    })


@tenant_access_required()
def ajax_acta_lineup(request, match_id):
    """
    Vista AJAX que devuelve convocados + alineaciones por set del acta oficial,
    enriquecidos con datos de Person/PlayerRole donde haya coincidencia de dorsal.
    """
    try:
        match = Match.objects.select_related(
            'home_team', 'away_team'
        ).get(id=match_id)
    except Match.DoesNotExist:
        return JsonResponse({'success': False, 'error': _('Partido no encontrado')}, status=404)

    acta_url = match.official_acta_url or match.acta_html
    if not acta_url:
        return JsonResponse({'success': False, 'error': _('Este partido no tiene acta disponible')}, status=404)

    # El acta se persiste en el partido: una vez parseada no se vuelve a
    # descargar y queda disponible para los históricos por jugador.
    lineup_data = match.acta_data
    if lineup_data is None:
        # Solo se cachea el parseo correcto; los errores de red se reintentan en la siguiente petición.
        cache_key = _acta_lineup_cache_key(acta_url)
        lineup_data = cache.get(cache_key)
        if lineup_data is None:
            try:
                acta_content = safe_get(
                    acta_url, allowed_hosts=settings.ACTA_ALLOWED_HOSTS,
                )
            except UnsafeURL as e:
                logger.warning(f"URL de acta rechazada para el partido {match_id}: {e}")
                return JsonResponse({'success': False, 'error': _('La URL del acta no es válida')}, status=400)
            except http_requests.exceptions.Timeout:
                return JsonResponse({'success': False, 'error': _('Tiempo de espera agotado al obtener el acta')}, status=504)
            except http_requests.exceptions.RequestException as e:
                logger.warning(f"Error obteniendo acta del partido {match_id}: {e}")
                return JsonResponse({'success': False, 'error': _('No se pudo acceder al acta oficial')}, status=502)

            try:
                # Pasar bytes para que BeautifulSoup detecte el charset del meta tag
                # (evita que requests decodifique mal UTF-8 como Latin-1)
                lineup_data = parse_acta_lineup(acta_content)
            except Exception as e:
                logger.error(f"Error parseando acta del partido {match_id}: {e}")
                return JsonResponse({'success': False, 'error': _('Error al procesar el acta')}, status=500)
            cache.set(cache_key, lineup_data, 60 * 60 * 24)

        store_match_lineups(match, lineup_data)

    # Pre-fetch todos los PlayerRole activos de ambos equipos en una sola query
    # acotando a personas de la organización actual para no exponer fotos ajenas
    roles_lookup = {}  # {(team_id, jersey_number): role}
    teams_to_query = [t for t in [match.home_team, match.away_team] if t]
    if teams_to_query:
        for role in (
            PlayerRole.objects
            .filter(
                team__in=teams_to_query,
                is_active=True,
                jersey_number__isnull=False,
                person__organizations=request.tenant,
            )
            .select_related('person', 'team')
        ):
            roles_lookup[(role.team_id, role.jersey_number)] = role

    def _person_data(role):
        if not role or not role.person:
            return None
        p = role.person
        return {
            'id': p.id,
            'full_name': p.full_name,
            'photo_url': p.photo.url if p.photo else None,
            'position': role.display_position if role.position else None,
        }

    def _match_team(name_acta):
        """Determina si name_acta corresponde al equipo local o visitante por solapamiento de palabras."""
        return resolve_acta_team(name_acta, match.home_team, match.away_team)

    def _enrich_convocados(raw_list, team):
        """["1 Raya", ...] → [{number, name_acta, person}]"""
        result = []
        for entry in raw_list:
            m = _re.match(r'^(\d+)\s+(.+)$', entry)
            if not m:
                result.append({'number': None, 'name_acta': entry, 'person': None})
                continue
            jersey = int(m.group(1))
            role = roles_lookup.get((team.id if team else None, jersey))
            result.append({
                'number': jersey,
                'name_acta': m.group(2),
                'person': _person_data(role),
            })
        return result

    def _enrich_lineup(lineup, team):
        """[{position, number, sub}] → [{position, number, sub, person}]"""
        result = []
        for entry in lineup:
            jersey = entry.get('number')
            role = roles_lookup.get((team.id if team else None, jersey)) if jersey is not None else None
            result.append({
                'position': entry.get('position'),
                'number': jersey,
                'sub': entry.get('sub'),
                'person': _person_data(role),
            })
        return result

    # Enriquecer sets: detectar home/away por nombre para cada equipo de cada set
    enriched_sets = []
    for set_data in lineup_data.get('sets', []):
        enriched_teams = []
        for team_data in set_data.get('teams', []):
            team_obj = _match_team(team_data['name'])
            enriched_teams.append({
                'name': team_data['name'],
                'is_home': team_obj == match.home_team,
                'lineup': _enrich_lineup(team_data['lineup'], team_obj),
                'points': team_data['points'],
            })
        enriched_sets.append({
            'title': set_data.get('title', ''),
            'time': set_data.get('time', ''),
            'teams': enriched_teams,
        })

    return JsonResponse({
        'success': True,
        'home_team': lineup_data.get('home_team', ''),
        'away_team': lineup_data.get('away_team', ''),
        'home_captain': lineup_data.get('home_captain', ''),
        'away_captain': lineup_data.get('away_captain', ''),
        'home_coach': lineup_data.get('home_coach', ''),
        'away_coach': lineup_data.get('away_coach', ''),
        'home_convocados': _enrich_convocados(lineup_data.get('home_convocados', []), match.home_team),
        'away_convocados': _enrich_convocados(lineup_data.get('away_convocados', []), match.away_team),
        'sets': enriched_sets,
        'referees': lineup_data.get('referees', []),
        'officials': lineup_data.get('officials', []),
        'observations': lineup_data.get('observations', ''),
    })


@tenant_access_required()
def standings_view(request):
    """Clasificación de las ligas principales, organizada en pestañas por categoría."""
    league_filter = request.GET.get('league')
    show_archived = request.GET.get('show_archived', '0') == '1'

    # Las pestañas comparan grupos de una misma categoría, también de otros clubes,
    # así que el alcance es global (ligas activas y principales), no por tenant.
    base_leagues_all = League.objects.all()
    base_leagues_visible = League.objects.filter(is_active=True, visibility_type='main')
    base_standings_all = Standing.objects.all()
    base_standings_visible = Standing.objects.filter(
        league__is_active=True,
        league__visibility_type='main',
    )
    current_season = Season.objects.current()
    if current_season:
        base_leagues_visible = base_leagues_visible.filter(
            Q(season=current_season) | Q(season__isnull=True)
        )
        base_standings_visible = base_standings_visible.filter(
            Q(league__season=current_season) | Q(league__season__isnull=True)
        )

    seasons = (
        base_leagues_all.filter(season__isnull=False)
        .values_list('season__name', flat=True)
        .distinct()
        .order_by('-season__name')
    )
    # Aquí la temporada se identifica por nombre (no por id como en el resto de
    # la app), de ahí el parámetro distinto `season_name` para no colisionar.
    season_filter = request.GET.get('season_name')
    if not season_filter:
        # Compatibilidad con el antiguo `?season=<nombre>`; se ignora si es un id.
        legacy = request.GET.get('season')
        if legacy and not legacy.isdigit():
            season_filter = legacy

    if show_archived or season_filter:
        # Mostrar ligas archivadas, de referencia, etc. O si se filtra por temporada específica
        # Ordenamos por fecha de creación descendente para ver las más recientes primero
        leagues = base_leagues_all.order_by('-created_at', 'name')
        standings = (
            base_standings_all
            .select_related('team', 'league')
            .prefetch_related('league__categories')
            .order_by('-league__created_at', 'league__name', 'position')
        )
    else:
        # Consulta base de clasificaciones - Solo ligas activas y visibles
        leagues = base_leagues_visible.order_by('name')
        standings = (
            base_standings_visible
            .select_related('team', 'league')
            .prefetch_related('league__categories')
            .order_by('league__name', 'position')
        )

    if season_filter:
        standings = standings.filter(league__season__name=season_filter)
        leagues = leagues.filter(season__name=season_filter)

    if league_filter:
        standings = standings.filter(league_id=league_filter)

    # Agrupar por liga y, después, por categoría (una liga aparece en cada una de las suyas)
    standings_by_league = {}
    for standing in standings:
        league_name = standing.league.display_name or standing.league.name
        if league_name not in standings_by_league:
            standings_by_league[league_name] = {
                'league': standing.league,
                'standings': []
            }
        standings_by_league[league_name]['standings'].append(standing)

    tabs = {}
    for league_name, league_data in standings_by_league.items():
        league_categories = list(league_data['league'].categories.all())
        for category in league_categories or [None]:
            name = category.name if category else _('Otras')
            tab = tabs.setdefault(name, {
                'name': name,
                'slug': slugify(name) if category else 'otras',  # slug estable, no traducido
                'category_id': category.id if category else None,
                'leagues': [],
            })
            tab['leagues'].append((league_name, league_data))
    category_tabs = sorted(tabs.values(), key=lambda t: (t['category_id'] is None, t['name']))

    # Pestaña inicial: la pedida por URL; si no, preferencias del usuario; si no,
    # primera categoría donde compite el club. El JS la sustituye por hash/localStorage.
    slugs = {t['slug'] for t in category_tabs}
    active_slug = request.GET.get('category')
    if active_slug not in slugs:
        preferred_ids = set(request.user.preferred_categories_for(request.tenant).values_list('id', flat=True))
        club_ids = set(
            League.objects.for_tenant(request.tenant, visible_only=True)
            .values_list('categories__id', flat=True)
        )
        active_slug = next(
            (t['slug'] for ids in (preferred_ids, club_ids) for t in category_tabs if t['category_id'] in ids),
            category_tabs[0]['slug'] if category_tabs else '',
        )

    return render(request, 'competitions/standings.html', {
        'standings_by_league': standings_by_league,
        'category_tabs': category_tabs,
        'active_slug': active_slug,
        'leagues': leagues,
        'seasons': seasons,
        'selected_league': league_filter,
        'selected_season': season_filter,
        'show_archived': show_archived,
        'club_team_name': get_primary_club_team_name(request.tenant),
    })


@tenant_access_required()
def ajax_matches_by_category(request):
    """Vista AJAX para obtener partidos filtrados por categoría"""
    category_id = request.GET.get('category_id')

    # Construir query base para equipos del club
    club_query = get_club_team_filter(request.tenant)

    # Si hay categoría específica, filtrar por equipos de esa categoría
    if category_id and category_id != '':
        try:
            category = Category.objects.get(id=category_id)
            # Filtrar por equipos que tengan la categoría específica O por liga de esa categoría
            category_query = (Q(home_team__category=category) | Q(away_team__category=category) |
                              Q(league__categories=category))

            # Combinar: partidos del club Y de la categoría específica
            final_query = club_query & category_query
        except Category.DoesNotExist:
            final_query = club_query
    else:
        # Sin categoría específica, mostrar todos los partidos del club
        final_query = club_query

    # Obtener partidos
    matches = Match.objects.select_related(
        'home_team', 'away_team', 'home_team__category', 'away_team__category',
        'league'
    ).prefetch_related('league__categories').filter(final_query).order_by('-match_date')[:50]  # Limitar a 50 partidos más recientes

    # Formatear respuesta
    matches_data = []
    for match in matches:
        league_name = match.league.name if match.league else _('Sin liga')
        matches_data.append({
            'id': match.id,
            'text': f"{match.home_team_display} vs {match.away_team_display} - {match.match_date.strftime('%d/%m/%Y')} ({league_name})"
        })

    return JsonResponse({
        'matches': matches_data
    })


@tenant_access_required(manager=True)
def ajax_teams_by_league_category(request):
    """Vista AJAX para obtener equipos filtrados por categoría de liga (para admin)"""
    league_id = request.GET.get('league_id')
    filter_by_category = request.GET.get('filter_by_category', 'true').lower() == 'true'

    if league_id and filter_by_category:
        try:
            league = League.objects.get(id=league_id)

            league_categories = league.categories.all()
            if league_categories.exists():
                # Filtrar equipos por las categorías de la liga
                teams = Team.objects.select_related('category').filter(category__in=league_categories).order_by('name')
            else:
                # Si la liga no tiene categorías, mostrar todos
                teams = Team.objects.select_related('category').all().order_by('name')
        except League.DoesNotExist:
            teams = Team.objects.select_related('category').all().order_by('name')
    else:
        # Sin filtrado o sin liga, mostrar todos los equipos
        teams = Team.objects.select_related('category').all().order_by('name')

    # Formatear respuesta
    teams_data = []
    for team in teams:
        display_name = team.name
        if team.category:
            display_name += f" ({team.category.name})"

        teams_data.append({
            'id': team.id,
            'text': display_name
        })

    return JsonResponse({
        'teams': teams_data
    })


@require_POST
@tenant_access_required(manager=True)
def match_share_create(request, match_id):
    """Crea un enlace público temporal para el partido."""
    match = get_tenant_object_or_404(
        Match.objects,
        request.tenant, user=request.user, id=match_id,
    )
    hours = request.POST.get('hours')
    create_match_share_link(match, request.tenant, request.user, hours=hours)
    messages.success(request, _('Enlace para compartir creado.'))
    return redirect('competitions:match_detail', match_id=match.id)


@tenant_access_required(manager=True)
@require_POST
def match_share_revoke(request, match_id, link_id):
    """Revoca un enlace público del partido."""
    match = get_tenant_object_or_404(
        Match.objects, request.tenant, user=request.user, id=match_id
    )
    link = get_object_or_404(
        MatchShareLink, id=link_id, match=match, organization=request.tenant
    )
    revoke_match_share_link(link)
    messages.success(request, _('Enlace revocado.'))
    return redirect('competitions:match_detail', match_id=match.id)


def public_match_timeline(request, token):
    """Ficha multimedia pública de un partido a partir de un enlace temporal."""
    link = resolve_match_share_link(token)
    if link is None:
        raise Http404
    match = link.match

    # Aislamiento de tenant: el enlace solo expone medios de su organización (los medios sin organización no se comparten públicamente por precaución).
    videos = list(
        match.videos.filter(organization_id=link.organization_id)
        .order_by('-created_at')
    )
    images = list(
        match.images.filter(status='approved', organization_id=link.organization_id)
        .order_by('-upload_date')
    )
    groups = group_match_media(videos, images, get_match_set_labels(match))
    has_media = any(group['videos'] or group['images'] for group in groups)

    response = render(request, 'competitions/public_match_timeline.html', {
        'link': link,
        'match': match,
        'groups': groups,
        'has_media': has_media,
    })
    response['Cache-Control'] = 'private, no-store'
    response['X-Robots-Tag'] = 'noindex, nofollow'
    return response


_VARIANT_FIELDS = {
    'thumb': 'thumbnail_small',
    'large': 'thumbnail_large',
    'orig': 'image',
}


def public_match_media(request, token, image_id):
    """Sirve una imagen aprobada del partido para un enlace temporal válido."""
    link = resolve_match_share_link(token)
    if link is None:
        raise Http404

    image = Image.objects.filter(
        id=image_id,
        match=link.match,
        status='approved',
        organization_id=link.organization_id,
    ).only(
        'image', 'thumbnail_small', 'thumbnail_large',
    ).first()
    if image is None:
        raise Http404

    field_name = _VARIANT_FIELDS.get(request.GET.get('v', 'thumb'), 'thumbnail_small')
    file_field = getattr(image, field_name, None) or image.image
    if not file_field or not file_field.name:
        raise Http404

    response = serve_protected_file(file_field.name)
    response['Cache-Control'] = 'private, no-store'
    response['X-Robots-Tag'] = 'noindex, nofollow'
    return response


def where_plays(request):
    """Página pública "Sedes y pabellones": equipos, próximos partidos y sedes.

    No requiere autenticación; se acota a la organización resuelta por el
    subdominio (``request.tenant``). El buscador funciona sin JS (envío normal
    del formulario) y con JS se refresca vía el endpoint JSON.
    """
    tenant = getattr(request, 'tenant', None)
    if tenant is None:
        return redirect('landing')

    query = (request.GET.get('q') or '').strip()
    results = search_locations(tenant, query) if len(query) >= MIN_QUERY_LENGTH else []
    return render(request, 'competitions/where_plays.html', {
        'query': query,
        'results': results,
        'min_query_length': MIN_QUERY_LENGTH,
    })


def where_plays_search(request):
    """Endpoint JSON del buscador en vivo de "Sedes y pabellones"."""
    tenant = getattr(request, 'tenant', None)
    if tenant is None:
        return JsonResponse({'results': []})

    query = (request.GET.get('q') or '').strip()
    if len(query) < MIN_QUERY_LENGTH:
        return JsonResponse({'results': [], 'min_query_length': MIN_QUERY_LENGTH})
    return JsonResponse({'results': search_locations(tenant, query)})


@tenant_access_required(manager=True)
def match_changes_review(request):
    """Panel de revisión de modificaciones federativas para directores/managers del club."""
    tenant = request.tenant
    season, selected_season_id = resolve_season_filter(request)

    qs = MatchChangeLog.objects.for_tenant(tenant).select_related(
        'match', 'match__league', 'match__home_team', 'match__away_team', 'reviewed_by'
    )

    if season:
        qs = qs.filter(match__league__season=season)

    status_filter = request.GET.get('status', 'pending')
    if status_filter == 'pending':
        qs = qs.filter(reviewed=False)
    elif status_filter == 'reviewed':
        qs = qs.filter(reviewed=True)

    change_type = request.GET.get('type')
    if change_type:
        qs = qs.filter(change_type=change_type)

    paginator = Paginator(qs, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    all_seasons = Season.objects.all().order_by('-start_year')

    pending_count = MatchChangeLog.objects.for_tenant(tenant)
    if season:
        pending_count = pending_count.filter(match__league__season=season)
    pending_count = pending_count.filter(reviewed=False).count()

    context = {
        'page_obj': page_obj,
        'changes': page_obj.object_list,
        'status_filter': status_filter,
        'selected_type': change_type or '',
        'selected_season_id': selected_season_id,
        'seasons': all_seasons,
        'pending_count': pending_count,
        'change_types': MatchChangeLog.CHANGE_TYPES,
    }
    return render(request, 'competitions/match_changes_review.html', context)


@require_POST
@tenant_access_required(manager=True, api=True)
def ajax_mark_change_reviewed(request, log_id):
    """Marca una modificación federativa como revisada por el director/manager actual."""
    tenant = getattr(request, 'tenant', None)
    log = get_object_or_404(MatchChangeLog.objects.for_tenant(tenant), pk=log_id)

    log.reviewed = True
    log.reviewed_by = request.user
    log.reviewed_at = timezone.now()
    log.save(update_fields=['reviewed', 'reviewed_by', 'reviewed_at'])

    return JsonResponse({
        'status': 'success',
        'log_id': log.id,
        'reviewed': True,
        'reviewed_by': request.user.get_full_name() or request.user.username,
        'reviewed_at': log.reviewed_at.strftime('%d/%m/%Y %H:%M'),
    })


@require_POST
@tenant_access_required(manager=True)
def ajax_update_stream_url(request, match_id):
    """Actualiza el enlace de retransmisión en directo del partido (#359)."""
    try:
        match = Match.objects.for_tenant(request.tenant).get(id=match_id)
    except Match.DoesNotExist:
        return JsonResponse({'success': False, 'error': _('Partido no encontrado')}, status=404)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': _('Datos inválidos')}, status=400)

    stream_url = (data.get('stream_url') or '').strip()

    if stream_url:
        validator = URLValidator(schemes=['http', 'https'])
        try:
            validator(stream_url)
        except ValidationError:
            return JsonResponse({
                'success': False,
                'error': _('La URL debe comenzar con http:// o https:// y tener un formato válido.'),
            }, status=400)

    match.stream_url = stream_url
    match.save(update_fields=['stream_url'])

    notified = False
    if stream_url and match.is_live_window and match.stream_notified_at is None:
        try:
            notified = notify_match_live_stream(match, tenant=request.tenant)
        except Exception:
            logger.exception("Error al notificar directo del partido %s", match_id)

    return JsonResponse({
        'success': True,
        'stream_url': match.stream_url,
        'notified': bool(notified),
        'is_live': match.is_live,
    })


__all__ = [
    'league_list',
    'league_detail',
    'match_detail',
    'match_share_create',
    'match_share_revoke',
    'public_match_timeline',
    'public_match_media',
    'where_plays',
    'where_plays_search',
    'match_result_card',
    'calendar_view',
    'friendly_match_create',
    'ajax_search_teams',
    'ajax_add_match_result',
    'ajax_edit_match_result',
    'ajax_acta_lineup',
    'ajax_update_stream_url',
    'standings_view',
    'ajax_matches_by_category',
    'ajax_teams_by_league_category',
    'match_changes_review',
    'ajax_mark_change_reviewed',
]

