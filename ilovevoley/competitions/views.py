import calendar
import json
import logging
import re as _re
from datetime import datetime, timedelta

import requests as http_requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Case, CharField, Q, Value, When
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from unidecode import unidecode as _uni

from ilovevoley.core.mixins import get_club_team_filter
from ilovevoley.core.models import Category
from ilovevoley.core.tenant_utils import tenant_access_required, user_is_tenant_manager
from ilovevoley.rosters.models import PlayerRole
from ilovevoley.teams.models import Team
from ilovevoley.videos.scraping import parse_acta_lineup
from .forms import FriendlyMatchForm, MatchResultForm
from .models import League, Match, Standing

logger = logging.getLogger(__name__)


@tenant_access_required()
def league_list(request):
    """Vista para mostrar todas las ligas disponibles"""
    leagues = League.objects.visible_in_app().prefetch_related('matches__videos')
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
    elif not show_all and request.user.preferred_categories.exists():
        user_categories = request.user.preferred_categories.all()
        leagues = leagues.filter(categories__in=user_categories).distinct()

    # Filtrar partidos amistosos si no se quiere mostrar
    if not show_friendly:
        # Excluir ligas de partidos amistosos
        leagues = leagues.exclude(competition_type='friendly')

    # Filtrar ligas pasadas si no se quiere mostrar
    if not show_past:
        # Solo mostrar ligas con partidos pendientes
        now = timezone.now()
        leagues = leagues.filter(
            matches__status__in=['scheduled', 'in_progress'],
            matches__match_date__gte=now
        ).distinct()

    # Ordenar: ligas oficiales primero, luego amistosas, y por nombre dentro de cada tipo
    leagues = leagues.annotate(
        sort_priority=Case(
            When(competition_type='friendly', then=Value(2)),
            default=Value(1),
            output_field=CharField(),
        )
    ).order_by('sort_priority', 'name')

    return render(request, 'competitions/league_list.html', {
        'leagues': leagues,
        'categories': categories,
        'selected_category': category_filter,
        'show_all': show_all,
        'show_friendly': show_friendly,
        'show_past': show_past,
        'has_preferences': request.user.preferred_categories.exists(),
    })


@tenant_access_required()
def league_detail(request, league_id):
    """Vista detallada de una liga con partidos y clasificación"""
    league = get_object_or_404(League, id=league_id, is_active=True)

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
        # Mostrar fase específica
        try:
            phase_league = League.objects.get(id=selected_phase)
            matches = Match.objects.filter(league=phase_league)
            display_league = phase_league
        except League.DoesNotExist:
            matches = Match.objects.filter(league=league)
            display_league = league
    else:
        # Mostrar solo esta liga
        matches = Match.objects.filter(league=league)
        display_league = league

    # Aplicar select_related y prefetch_related
    matches = matches.select_related('home_team', 'away_team', 'league').prefetch_related('videos').order_by('-match_date')

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
        id=match_id
    )

    # Obtener videos del partido
    videos = match.videos.select_related('created_by', 'category').all()

    # Obtener imágenes aprobadas del partido
    images = match.images.filter(status='approved').select_related('uploaded_by').all()

    return render(request, 'competitions/match_detail.html', {
        'match': match,
        'videos': videos,
        'images': images,
        'today': timezone.now().date(),
        'can_manage_videos': user_is_tenant_manager(request.user, request.tenant),
    })


@tenant_access_required()
def calendar_view(request):
    """Vista del calendario de partidos"""
    # Obtener filtros
    show_all_teams = request.GET.get('all_teams', '0') == '1'
    show_all = request.GET.get('show_all', '0') == '1'
    league_filter = request.GET.get('league')
    category_filter = request.GET.get('category')

    # Consulta base de partidos (withdrawn excluidos automáticamente por el manager)
    matches = Match.objects.select_related(
        'home_team', 'away_team', 'league'
    ).prefetch_related('league__categories').order_by('match_date')

    # Filtrar por equipo del club por defecto
    if not show_all_teams:
        matches = matches.filter(get_club_team_filter(request.tenant))

    # Aplicar filtro de liga
    if league_filter:
        matches = matches.filter(league_id=league_filter)

    # Aplicar filtro de categoría
    if category_filter:
        matches = matches.filter(league__categories__id=category_filter).distinct()
    # Si no hay filtro de categoría, aplicar preferencias del usuario
    elif not show_all and request.user.preferred_categories.exists():
        user_categories = request.user.preferred_categories.all()
        matches = matches.filter(league__categories__in=user_categories).distinct()

    # Obtener datos para filtros
    leagues = League.objects.visible_in_app().order_by('name')
    categories = Category.objects.filter(is_active=True).order_by('name')

    # Obtener el mes actual o el solicitado
    year = int(request.GET.get('year', timezone.now().year))
    month = int(request.GET.get('month', timezone.now().month))

    # Filtrar partidos del mes seleccionado
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = datetime(year, month + 1, 1) - timedelta(days=1)

    monthly_matches = matches.filter(
        match_date__date__gte=start_date.date(),
        match_date__date__lte=end_date.date()
    )

    # Navegación de meses
    prev_month = start_date - timedelta(days=1)
    next_month = end_date + timedelta(days=1)

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
        1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
        5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
        9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
    }

    return render(request, 'competitions/calendar.html', {
        'matches': monthly_matches,
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
        'has_preferences': request.user.preferred_categories.exists(),
        'today': timezone.now().date(),
    })


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
                f'Partido amistoso creado: {match.home_team_display} vs {match.away_team_display}'
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


@login_required
def ajax_search_teams(request):
    """Vista AJAX para buscar equipos con autocompletado inteligente"""
    query = request.GET.get('q', '').strip()
    category_id = request.GET.get('category_id', '').strip()

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

    # Limitar a 10 resultados
    teams = teams_query.order_by('name')[:10]

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


@tenant_access_required(manager=True)
def ajax_add_match_result(request, match_id):
    """Vista AJAX para agregar resultado de partido"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)

    try:
        match = Match.objects.get(id=match_id)
    except Match.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Partido no encontrado'}, status=404)

    # Verificar que el partido no tenga resultado ya
    if match.is_finished and match.home_score is not None and match.away_score is not None:
        return JsonResponse({'success': False, 'error': 'Este partido ya tiene resultado'}, status=400)

    # Verificar que el partido ya haya pasado o sea hoy
    if match.match_date.date() > timezone.now().date():
        return JsonResponse({'success': False, 'error': 'No se puede agregar resultado a un partido futuro'}, status=400)

    # Parsear datos JSON
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Datos inválidos'}, status=400)

    # Crear formulario con los datos
    form = MatchResultForm(data, instance=match)

    if form.is_valid():
        try:
            match = form.save()
            return JsonResponse({
                'success': True,
                'message': f'Resultado guardado: {match.result_display}',
                'result_display': match.result_display,
                'home_score': match.home_score,
                'away_score': match.away_score
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Error al guardar: {str(e)}'}, status=500)
    else:
        # Recopilar errores del formulario
        errors = {}
        for field, field_errors in form.errors.items():
            errors[field] = field_errors[0] if field_errors else 'Error desconocido'

        return JsonResponse({
            'success': False,
            'error': 'Datos inválidos',
            'errors': errors
        }, status=400)


@tenant_access_required()
def ajax_acta_lineup(request, match_id):
    """
    Vista AJAX que devuelve convocados + alineaciones por set del acta oficial,
    enriquecidos con datos de Person/PlayerRole donde haya coincidencia de dorsal.
    """
    try:
        match = Match.objects.select_related('home_team', 'away_team').get(id=match_id)
    except Match.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Partido no encontrado'}, status=404)

    if not match.acta_html:
        return JsonResponse({'success': False, 'error': 'Este partido no tiene acta disponible'}, status=404)

    try:
        response = http_requests.get(match.acta_html, timeout=10)
        response.raise_for_status()
    except http_requests.exceptions.Timeout:
        return JsonResponse({'success': False, 'error': 'Tiempo de espera agotado al obtener el acta'}, status=504)
    except http_requests.exceptions.RequestException as e:
        logger.warning(f"Error obteniendo acta del partido {match_id}: {e}")
        return JsonResponse({'success': False, 'error': 'No se pudo acceder al acta oficial'}, status=502)

    try:
        # Pasar bytes para que BeautifulSoup detecte el charset del meta tag
        # (evita que requests decodifique mal UTF-8 como Latin-1)
        lineup_data = parse_acta_lineup(response.content)
    except Exception as e:
        logger.error(f"Error parseando acta del partido {match_id}: {e}")
        return JsonResponse({'success': False, 'error': 'Error al procesar el acta'}, status=500)

    # Pre-fetch todos los PlayerRole activos de ambos equipos en una sola query
    roles_lookup = {}  # {(team_id, jersey_number): role}
    teams_to_query = [t for t in [match.home_team, match.away_team] if t]
    if teams_to_query:
        for role in (
            PlayerRole.objects
            .filter(team__in=teams_to_query, is_active=True, jersey_number__isnull=False)
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
        def words(s):
            return set(_uni(s or '').upper().split())
        n = words(name_acta)
        nh = words(match.home_team.name if match.home_team else '')
        na = words(match.away_team.name if match.away_team else '')
        return match.home_team if len(n & nh) >= len(n & na) else match.away_team

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
            'title': set_data['title'],
            'time': set_data['time'],
            'teams': enriched_teams,
        })

    return JsonResponse({
        'success': True,
        'home_team': lineup_data['home_team'],
        'away_team': lineup_data['away_team'],
        'home_captain': lineup_data['home_captain'],
        'away_captain': lineup_data['away_captain'],
        'home_convocados': _enrich_convocados(lineup_data['home_convocados'], match.home_team),
        'away_convocados': _enrich_convocados(lineup_data['away_convocados'], match.away_team),
        'sets': enriched_sets,
    })


@tenant_access_required()
def standings_view(request):
    """Vista de clasificación de las ligas"""
    # Obtener filtros
    league_filter = request.GET.get('league')
    category_filter = request.GET.get('category')
    show_all = request.GET.get('show_all', '0') == '1'
    show_archived = request.GET.get('show_archived', '0') == '1'

    # Obtener temporadas disponibles
    seasons = (
        League.objects.filter(is_our_team_related=True, season__isnull=False)
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
        standings = Standing.objects.select_related(
            'team', 'league'
        ).prefetch_related('league__categories').order_by('-league__created_at', 'league__name', 'position')

        # Filtro de ligas para el dropdown
        leagues = League.objects.all().order_by('-created_at', 'name')
    else:
        # Consulta base de clasificaciones - Solo ligas activas y visibles en app
        standings = Standing.objects.filter(
            league__is_active=True,
            league__visibility_type='main',
            league__is_our_team_related=True
        ).select_related(
            'team', 'league'
        ).prefetch_related('league__categories').order_by('league__name', 'position')

        # Filtro de ligas para el dropdown
        leagues = League.objects.visible_in_app().order_by('name')

    # Aplicar filtro de temporada
    if season_filter:
        standings = standings.filter(league__season__name=season_filter)
        # También filtrar las ligas del dropdown por temporada
        leagues = leagues.filter(season__name=season_filter)

    # Aplicar filtro de liga
    if league_filter:
        standings = standings.filter(league_id=league_filter)

    # Aplicar filtro de categoría
    if category_filter:
        standings = standings.filter(league__categories__id=category_filter)
    # Si no hay filtro de categoría, aplicar preferencias del usuario
    elif not show_all and request.user.preferred_categories.exists():
        user_categories = request.user.preferred_categories.all()
        standings = standings.filter(league__categories__in=user_categories)

    # Agrupar por liga
    standings_by_league = {}
    for standing in standings:
        league_name = standing.league.name
        if standing.league.display_name:
            league_name = standing.league.display_name

        if league_name not in standings_by_league:
            standings_by_league[league_name] = {
                'league': standing.league,
                'standings': []
            }
        standings_by_league[league_name]['standings'].append(standing)

    categories = Category.objects.filter(is_active=True).order_by('name')

    return render(request, 'competitions/standings.html', {
        'standings_by_league': standings_by_league,
        'leagues': leagues,
        'categories': categories,
        'seasons': seasons,
        'selected_league': league_filter,
        'selected_category': category_filter,
        'selected_season': season_filter,
        'show_all': show_all,
        'show_archived': show_archived,
        'has_preferences': request.user.preferred_categories.exists(),
    })


@login_required
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
        league_name = match.league.name if match.league else 'Sin liga'
        matches_data.append({
            'id': match.id,
            'text': f"{match.home_team_display} vs {match.away_team_display} - {match.match_date.strftime('%d/%m/%Y')} ({league_name})"
        })

    return JsonResponse({
        'matches': matches_data
    })


@login_required
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
                teams = Team.objects.filter(category__in=league_categories).order_by('name')
            else:
                # Si la liga no tiene categorías, mostrar todos
                teams = Team.objects.all().order_by('name')
        except League.DoesNotExist:
            teams = Team.objects.all().order_by('name')
    else:
        # Sin filtrado o sin liga, mostrar todos los equipos
        teams = Team.objects.all().order_by('name')

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


__all__ = [
    'league_list',
    'league_detail',
    'match_detail',
    'calendar_view',
    'friendly_match_create',
    'ajax_search_teams',
    'ajax_add_match_result',
    'ajax_acta_lineup',
    'standings_view',
    'ajax_matches_by_category',
    'ajax_teams_by_league_category',
]
