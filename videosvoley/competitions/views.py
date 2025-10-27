"""
Views para la gestión de competiciones (ligas, partidos, calendario, clasificaciones).
Migradas desde videos.views para la nueva app competitions.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Case, When, Value, CharField
from django.http import JsonResponse
from django.conf import settings
from django.views.decorators.http import require_POST
from django.utils import timezone
from datetime import datetime, timedelta
import calendar
import logging

from .models import League, Match, Standing, ScrapingEndpoint
from .forms import FriendlyMatchForm, MatchResultForm

# Importar modelos de otras apps
from videosvoley.content.models import Category
from videosvoley.teams.models import Team

# Configurar logger
logger = logging.getLogger(__name__)


def user_is_approved(user):
    """Verifica si el usuario está aprobado para acceder al contenido"""
    return user.is_approved


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
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
        leagues = leagues.filter(category_id=category_filter)
    # Filtrar por categorías preferidas del usuario si no se especifica otra cosa
    elif not show_all and request.user.preferred_categories.exists():
        user_categories = request.user.preferred_categories.all()
        leagues = leagues.filter(category__in=user_categories)
    
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


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def league_detail(request, league_id):
    """Vista detallada de una liga con partidos y clasificación"""
    league = get_object_or_404(League, id=league_id, is_active=True)
    
    # Obtener partidos de la liga
    matches = Match.objects.filter(league=league).select_related(
        'home_team', 'away_team'
    ).prefetch_related('videos').order_by('-match_date')
    
    # Obtener clasificación
    standings = league.standings.select_related('team').order_by('position')
    
    # Filtros opcionales
    round_filter = request.GET.get('round')
    if round_filter:
        matches = matches.filter(round_number=round_filter)
    
    # Filtro de solo partidos con videos
    with_videos = request.GET.get('with_videos')
    if with_videos:
        matches = matches.filter(videos__isnull=False).distinct()
    
    # Obtener jornadas disponibles
    available_rounds = matches.values_list('round_number', flat=True).distinct().order_by('round_number')
    
    # Paginación de partidos
    paginator = Paginator(matches, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'competitions/league_detail.html', {
        'league': league,
        'page_obj': page_obj,
        'standings': standings,
        'available_rounds': available_rounds,
        'selected_round': round_filter,
        'with_videos': with_videos
    })


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def match_detail(request, match_id):
    """Vista detallada de un partido con sus videos"""
    match = get_object_or_404(
        Match.objects.select_related('home_team', 'away_team', 'league'), 
        id=match_id
    )
    
    # Obtener videos del partido
    videos = match.videos.select_related('created_by', 'category').all()
    
    return render(request, 'competitions/match_detail.html', {
        'match': match,
        'videos': videos,
        'today': timezone.now().date()
    })


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def calendar_view(request):
    """Vista del calendario de partidos"""
    # Configuración del club
    CLUB_TEAM_NAME = 'SANT JOSEP'
    
    # Obtener filtros
    show_all_teams = request.GET.get('all_teams', '0') == '1'
    show_all = request.GET.get('show_all', '0') == '1'
    league_filter = request.GET.get('league')
    category_filter = request.GET.get('category')
    
    # Consulta base de partidos (withdrawn excluidos automáticamente por el manager)
    matches = Match.objects.select_related(
        'home_team', 'away_team', 'league', 'league__category'
    ).order_by('match_date')
    
    # Filtrar por equipo del club por defecto
    if not show_all_teams:
        matches = matches.filter(
            Q(home_team__name__icontains=CLUB_TEAM_NAME) | 
            Q(away_team__name__icontains=CLUB_TEAM_NAME) |
            Q(home_team_text__icontains=CLUB_TEAM_NAME) |
            Q(away_team_text__icontains=CLUB_TEAM_NAME)
        )
    
    # Aplicar filtro de liga
    if league_filter:
        matches = matches.filter(league_id=league_filter)
    
    # Aplicar filtro de categoría
    if category_filter:
        matches = matches.filter(league__category_id=category_filter)
    # Si no hay filtro de categoría, aplicar preferencias del usuario
    elif not show_all and request.user.preferred_categories.exists():
        user_categories = request.user.preferred_categories.all()
        matches = matches.filter(league__category__in=user_categories)
    
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
        'club_team_name': CLUB_TEAM_NAME,
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


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
@user_passes_test(lambda u: u.is_staff or u.groups.filter(name='VideoManagers').exists(), login_url='/')
def friendly_match_create(request):
    """Vista para crear un partido amistoso"""
    if request.method == 'POST':
        # Debug: ver qué datos estamos recibiendo
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
            # Mostrar errores con más detalle
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


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
@user_passes_test(lambda u: u.is_staff or u.groups.filter(name='VideoManagers').exists(), login_url='/')
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
        import json
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


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def standings_view(request):
    """Vista de clasificación de las ligas"""
    # Obtener filtros
    league_filter = request.GET.get('league')
    category_filter = request.GET.get('category')
    show_all = request.GET.get('show_all', '0') == '1'
    
    # Configuración del club
    CLUB_TEAM_NAME = 'SANT JOSEP'
    
    # Consulta base de clasificaciones
    standings = Standing.objects.select_related(
        'team', 'league', 'league__category'
    ).order_by('league__name', 'position')
    
    # Aplicar filtro de liga
    if league_filter:
        standings = standings.filter(league_id=league_filter)
    
    # Aplicar filtro de categoría
    if category_filter:
        standings = standings.filter(league__category_id=category_filter)
    # Si no hay filtro de categoría, aplicar preferencias del usuario
    elif not show_all and request.user.preferred_categories.exists():
        user_categories = request.user.preferred_categories.all()
        standings = standings.filter(league__category__in=user_categories)
    
    # Agrupar por liga
    standings_by_league = {}
    for standing in standings:
        league_name = standing.league.name
        if league_name not in standings_by_league:
            standings_by_league[league_name] = {
                'league': standing.league,
                'standings': []
            }
        standings_by_league[league_name]['standings'].append(standing)
    
    # Obtener datos para filtros
    leagues = League.objects.visible_in_app().order_by('name')
    categories = Category.objects.filter(is_active=True).order_by('name')
    
    return render(request, 'competitions/standings.html', {
        'standings_by_league': standings_by_league,
        'leagues': leagues,
        'categories': categories,
        'selected_league': league_filter,
        'selected_category': category_filter,
        'club_team_name': CLUB_TEAM_NAME,
        'show_all': show_all,
        'has_preferences': request.user.preferred_categories.exists(),
    })


@login_required
def ajax_matches_by_category(request):
    """Vista AJAX para obtener partidos filtrados por categoría"""
    category_id = request.GET.get('category_id')
    club_team_name = getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')
    
    # Construir query base para equipos del club
    club_query = (
        Q(home_team__name__icontains=club_team_name) | 
        Q(away_team__name__icontains=club_team_name) |
        Q(home_team_text__icontains=club_team_name) |
        Q(away_team_text__icontains=club_team_name)
    )
    
    # Si hay categoría específica, filtrar por equipos de esa categoría
    if category_id and category_id != '':
        try:
            category = Category.objects.get(id=category_id)
            # Filtrar por equipos que tengan la categoría específica O por liga de esa categoría
            category_query = (Q(home_team__category=category) | Q(away_team__category=category) |
                            Q(league__category=category))
            
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
        'league', 'league__category'
    ).filter(final_query).order_by('-match_date')[:50]  # Limitar a 50 partidos más recientes
    
    # Formatear respuesta
    matches_data = []
    for match in matches:
        matches_data.append({
            'id': match.id,
            'text': f"{match.home_team_display} vs {match.away_team_display} - {match.match_date.strftime('%d/%m/%Y')} ({match.league.name})"
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
            
            if league.category:
                # Filtrar equipos por la categoría de la liga
                teams = Team.objects.filter(category=league.category).order_by('name')
            else:
                # Si la liga no tiene categoría, mostrar todos
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


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def ajax_register_team(request):
    """Vista AJAX para registrar un nuevo equipo desde el formulario de amistosos"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)
    
    try:
        team_name = request.POST.get('name', '').strip()
        category_id = request.POST.get('category_id', '').strip()
        club_id = request.POST.get('club_id', '').strip()
        
        if not team_name:
            return JsonResponse({'success': False, 'error': 'El nombre del equipo es requerido'})
        
        if not category_id:
            return JsonResponse({'success': False, 'error': 'La categoría es requerida'})
        
        # Validar categoría
        try:
            category = Category.objects.get(id=category_id, is_active=True)
        except Category.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Categoría no válida'})
        
        # Validar club si se proporciona
        club = None
        if club_id:
            try:
                from videosvoley.teams.models import Club
                club = Club.objects.get(id=club_id)
            except Club.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Club no válido'})
        
        # Verificar si ya existe un equipo con el mismo nombre en la misma categoría
        existing_team = Team.objects.filter(name__iexact=team_name, category=category).first()
        if existing_team:
            return JsonResponse({
                'success': False, 
                'error': f'Ya existe un equipo llamado "{team_name}" en la categoría {category.name}',
                'existing_team': {
                    'id': existing_team.id,
                    'name': existing_team.name,
                    'club': existing_team.club.official_name if existing_team.club else None
                }
            })
        
        # Crear nuevo equipo
        new_team = Team.objects.create(
            name=team_name,
            category=category,
            club=club,
            is_active=True
        )
        
        logger.info(f"Equipo registrado: {new_team.name} ({category.name}) por usuario {request.user.username}")
        
        return JsonResponse({
            'success': True,
            'message': f'Equipo "{team_name}" registrado correctamente en {category.name}',
            'team': {
                'id': new_team.id,
                'name': new_team.name,
                'category': category.name,
                'club': club.official_name if club else None,
                'display': f"{new_team.name} ({category.name})" + (f" - {club.official_name}" if club else "")
            }
        })
        
    except Exception as e:
        logger.error(f"Error registrando equipo: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Error interno del servidor'
        }, status=500)