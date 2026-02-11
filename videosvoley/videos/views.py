from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.contrib.postgres.search import TrigramSimilarity
from django.http import JsonResponse
from django.conf import settings
from django.views.decorators.http import require_POST
from unidecode import unidecode
from datetime import datetime, timedelta
import calendar
from django.utils import timezone
import logging
import base64
import uuid
from django.core.files.base import ContentFile
from .models import Video, Comment, Category, League, Match, Team, Standing, Image, Player, Staff, Person, PlayerRole, StaffRole
from .forms import VideoForm, CommentForm, ImageUploadForm, ImageFilterForm, ImageModerationForm, FriendlyMatchForm, PersonForm, PlayerRoleForm, StaffRoleForm, MatchResultForm
from .utils import process_uploaded_image

# Configurar logger
logger = logging.getLogger(__name__)


def user_is_approved(user):
    """Verifica si el usuario está aprobado para acceder al contenido"""
    return user.is_approved


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def video_list(request):
    videos = Video.objects.select_related('category', 'created_by', 'match__home_team', 'match__away_team', 'match__league').prefetch_related('comments').all()
    categories = Category.objects.filter(is_active=True)
    leagues = League.objects.visible_in_app()
    teams = Team.objects.all()
    
    # Filtros
    category_filter = request.GET.get('category')
    league_filter = request.GET.get('league')
    team_filter = request.GET.get('team')
    search_query = request.GET.get('search', '').strip()
    show_all = request.GET.get('show_all', '0') == '1'
    
    # Filtrar por categorías preferidas del usuario si no se especifica otra cosa
    if not category_filter and not show_all and request.user.preferred_categories.exists():
        user_categories = request.user.preferred_categories.all()
        videos = videos.filter(category__in=user_categories)
    
    # Aplicar filtro de categoría
    if category_filter:
        videos = videos.filter(category_id=category_filter)
    
    # Aplicar filtro de liga
    if league_filter:
        videos = videos.filter(match__league_id=league_filter)
    
    # Aplicar filtro de equipo
    if team_filter:
        videos = videos.filter(
            Q(match__home_team_id=team_filter) | 
            Q(match__away_team_id=team_filter)
        )
    
    # Aplicar búsqueda de texto (case-insensitive, accent-insensitive)
    if search_query:
        # Buscar en título, descripción y equipos
        videos = videos.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(match__home_team__name__icontains=search_query) |
            Q(match__away_team__name__icontains=search_query) |
            Q(match__home_team_text__icontains=search_query) |
            Q(match__away_team_text__icontains=search_query)
        )
    
    # Paginación
    paginator = Paginator(videos, 12)  # 12 videos por página
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    can_add = request.user.groups.filter(name='VideoManagers').exists()
    
    # Mensaje de prueba para verificar el sistema de toast (solo para desarrollo)
    if request.GET.get('test_toast'):
        test_type = request.GET.get('test_toast')
        if test_type == 'success':
            messages.success(request, '¡Toast de éxito funcionando correctamente!')
        elif test_type == 'error':
            messages.error(request, 'Toast de error funcionando correctamente')
        elif test_type == 'warning':
            messages.warning(request, 'Toast de advertencia funcionando correctamente')
        elif test_type == 'info':
            messages.info(request, 'Toast de información funcionando correctamente')
    
    return render(request, 'videos/video_list.html', {
        'page_obj': page_obj,
        'categories': categories,
        'leagues': leagues,
        'teams': teams,
        'selected_category': category_filter,
        'selected_league': league_filter,
        'selected_team': team_filter,
        'search_query': search_query,
        'can_add': can_add,
        'show_all': show_all,
        'has_preferences': request.user.preferred_categories.exists(),
    })


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
@user_passes_test(lambda u: u.groups.filter(name='VideoManagers').exists())
def video_create(request):
    if request.method == 'POST':
        form = VideoForm(request.POST)
        if form.is_valid():
            video = form.save(commit=False)
            video.created_by = request.user
            video.save()
            messages.success(request, 'Vídeo añadido correctamente')
            return redirect('videos:video_list')
    else:
        form = VideoForm()

    return render(request, 'videos/video_form.html', {'form': form})


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def video_detail(request, video_id):
    video = get_object_or_404(Video, id=video_id)
    
    # Manejar envío de comentarios
    if request.method == 'POST':
        comment_form = CommentForm(request.POST)
        if comment_form.is_valid():
            comment = comment_form.save(commit=False)
            comment.video = video
            comment.user = request.user
            comment.save()
            messages.success(request, '¡Comentario añadido correctamente!')
            return redirect('video_detail', video_id=video.id)
    else:
        comment_form = CommentForm()
    
    # Cargar comentarios con información del usuario
    comments = video.comments.select_related('user').all()
    
    return render(request, 'videos/video_detail.html', {
        'video': video,
        'comments': comments,
        'comment_form': comment_form
    })


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
        from django.utils import timezone
        now = timezone.now()
        leagues = leagues.filter(
            matches__status__in=['scheduled', 'in_progress'],
            matches__match_date__gte=now
        ).distinct()
    
    # Ordenar: ligas oficiales primero, luego amistosas, y por nombre dentro de cada tipo
    from django.db.models import Case, When, Value, CharField
    leagues = leagues.annotate(
        sort_priority=Case(
            When(competition_type='friendly', then=Value(2)),
            default=Value(1),
            output_field=CharField(),
        )
    ).order_by('sort_priority', 'name')
    
    return render(request, 'videos/league_list.html', {
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
    if with_videos:
        matches = matches.filter(videos__isnull=False).distinct()

    available_rounds = matches.values_list('round_number', flat=True).distinct().order_by('round_number')

    # Paginación
    paginator = Paginator(matches, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'videos/league_detail.html', {
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


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
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

    return render(request, 'videos/match_detail.html', {
        'match': match,
        'videos': videos,
        'images': images,
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
        'home_team', 'away_team', 'league'
    ).prefetch_related('league__categories').order_by('match_date')
    
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
        matches = matches.filter(league__categories__id=category_filter)
    # Si no hay filtro de categoría, aplicar preferencias del usuario
    elif not show_all and request.user.preferred_categories.exists():
        user_categories = request.user.preferred_categories.all()
        matches = matches.filter(league__categories__in=user_categories)
    
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
    
    return render(request, 'videos/calendar.html', {
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
            return redirect('videos:calendar_view')
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
    
    return render(request, 'videos/friendly_match_form.html', {
        'form': form,
    })


@login_required
def ajax_search_teams(request):
    """Vista AJAX para buscar equipos con autocompletado inteligente"""
    from django.http import JsonResponse
    
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
    from django.http import JsonResponse
    from django.views.decorators.csrf import csrf_exempt
    import json
    
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


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def standings_view(request):
    """Vista de clasificación de las ligas"""
    # Obtener filtros
    league_filter = request.GET.get('league')
    category_filter = request.GET.get('category')
    show_all = request.GET.get('show_all', '0') == '1'
    show_archived = request.GET.get('show_archived', '0') == '1'
    
    # Configuración del club
    CLUB_TEAM_NAME = 'SANT JOSEP'
    
    # Obtener temporadas disponibles
    seasons = League.objects.filter(is_our_team_related=True).values_list('season', flat=True).distinct().order_by('-season')
    season_filter = request.GET.get('season')

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
        standings = standings.filter(league__season=season_filter)
        # También filtrar las ligas del dropdown por temporada
        leagues = leagues.filter(season=season_filter)
    
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
    
    return render(request, 'videos/standings.html', {
        'standings_by_league': standings_by_league,
        'leagues': leagues,
        'categories': categories,
        'seasons': seasons,
        'selected_league': league_filter,
        'selected_category': category_filter,
        'selected_season': season_filter,
        'club_team_name': CLUB_TEAM_NAME,
        'show_all': show_all,
        'show_archived': show_archived,
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
            from .models import League
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


# ===============================
# VISTAS DE GESTIÓN DE IMÁGENES
# ===============================

@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def image_gallery(request):
    """Vista de galería de imágenes con filtros"""
    images = Image.objects.select_related(
        'match__home_team', 'match__away_team', 'match__league', 
        'uploaded_by'
    ).prefetch_related('categories').filter(status='approved').order_by('-upload_date')
    
    # Variable para controlar si mostrar todo el contenido
    show_all = request.GET.get('show_all', '0') == '1'
    
    # Aplicar filtros
    filter_form = ImageFilterForm(request.GET)
    if filter_form.is_valid():
        search = filter_form.cleaned_data.get('search')
        tags = filter_form.cleaned_data.get('tags')
        image_type = filter_form.cleaned_data.get('image_type')
        match_filter = filter_form.cleaned_data.get('match_filter')
        category = filter_form.cleaned_data.get('category')
        year = filter_form.cleaned_data.get('year')
        status_filter = filter_form.cleaned_data.get('status')
        
        # Búsqueda general en título, descripción y etiquetas
        if search:
            images = images.filter(
                Q(title__icontains=search) | 
                Q(description__icontains=search) |
                Q(tags__icontains=search)
            )
        
        # Búsqueda específica por etiquetas (incluye auto_tags)
        if tags:
            tag_queries = Q()
            for tag in tags.split(','):
                tag = tag.strip()
                if tag:
                    tag_queries |= (
                        Q(tags__icontains=tag) |
                        Q(auto_tags__icontains=tag)
                    )
            images = images.filter(tag_queries)
        
        # Filtro por tipo de imagen
        if image_type:
            images = images.filter(image_type=image_type)
        
        # Filtro por partido vinculado
        if match_filter == 'with_match':
            images = images.filter(match__isnull=False)
        elif match_filter == 'without_match':
            images = images.filter(match__isnull=True)
        
        if category:
            images = images.filter(categories=category)
        elif not show_all and request.user.preferred_categories.exists():
            # Filtrar por preferencias solo si no hay filtro de categoría específico
            user_categories = request.user.preferred_categories.all()
            images = images.filter(categories__in=user_categories).distinct()
            
        if year:
            images = images.filter(year=year)
            
        if status_filter:
            images = images.filter(status=status_filter)
    else:
        # Si no hay filtros válidos, aplicar preferencias por defecto
        if not show_all and request.user.preferred_categories.exists():
            user_categories = request.user.preferred_categories.all()
            images = images.filter(categories__in=user_categories).distinct()
    
    # Paginación
    paginator = Paginator(images, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Estadísticas para la vista
    total_images = Image.objects.filter(status='approved').count()
    pending_images = Image.objects.filter(status='pending').count()
    images_with_match = Image.objects.filter(status='approved', match__isnull=False).count()
    images_without_match = Image.objects.filter(status='approved', match__isnull=True).count()
    
    # Obtener etiquetas populares para sugerencias
    popular_tags = []
    try:
        # Recopilar todas las etiquetas manuales
        manual_tags = []
        for image in Image.objects.filter(status='approved').exclude(tags=''):
            manual_tags.extend([tag.strip().lower() for tag in image.tags.split(',') if tag.strip()])
        
        # Recopilar etiquetas automáticas
        auto_tags = []
        for image in Image.objects.filter(status='approved').exclude(auto_tags=[]):
            if isinstance(image.auto_tags, list):
                auto_tags.extend([tag.lower() for tag in image.auto_tags])
        
        # Combinar y contar frecuencias
        from collections import Counter
        all_tags = manual_tags + auto_tags
        if all_tags:
            tag_counts = Counter(all_tags)
            popular_tags = [tag for tag, count in tag_counts.most_common(15)]
    except Exception as e:
        print(f"Error obteniendo etiquetas populares: {e}")
    
    context = {
        'page_obj': page_obj,
        'filter_form': filter_form,
        'total_images': total_images,
        'pending_images': pending_images,
        'images_with_match': images_with_match,
        'images_without_match': images_without_match,
        'popular_tags': popular_tags,
        'current_filters': request.GET.dict(),
        'show_all': show_all,
        'has_preferences': request.user.preferred_categories.exists(),
        'view_mode': 'individual',
    }
    
    return render(request, 'videos/image_gallery.html', context)


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def image_gallery_albums(request):
    """Vista de galería de imágenes agrupadas por partido (álbumes)"""
    from django.db.models import Count, Prefetch
    
    # Obtener imágenes con sus partidos relacionados
    images = Image.objects.select_related(
        'match__home_team', 'match__away_team', 'match__league', 
        'uploaded_by'
    ).prefetch_related('categories').filter(status='approved').order_by('-upload_date')
    
    # Variable para controlar si mostrar todo el contenido
    show_all = request.GET.get('show_all', '0') == '1'
    
    # Aplicar filtros (reutilizar lógica de image_gallery)
    filter_form = ImageFilterForm(request.GET)
    if filter_form.is_valid():
        search = filter_form.cleaned_data.get('search')
        tags = filter_form.cleaned_data.get('tags')
        image_type = filter_form.cleaned_data.get('image_type')
        match_filter = filter_form.cleaned_data.get('match_filter')
        category = filter_form.cleaned_data.get('category')
        year = filter_form.cleaned_data.get('year')
        status_filter = filter_form.cleaned_data.get('status')
        
        # Búsqueda general en título, descripción y etiquetas
        if search:
            images = images.filter(
                Q(title__icontains=search) | 
                Q(description__icontains=search) |
                Q(tags__icontains=search)
            )
        
        # Búsqueda específica por etiquetas (incluye auto_tags)
        if tags:
            tag_queries = Q()
            for tag in tags.split(','):
                tag = tag.strip()
                if tag:
                    tag_queries |= (
                        Q(tags__icontains=tag) |
                        Q(auto_tags__icontains=tag)
                    )
            images = images.filter(tag_queries)
        
        # Filtro por tipo de imagen
        if image_type:
            images = images.filter(image_type=image_type)
        
        # Filtro por partido vinculado
        if match_filter == 'with_match':
            images = images.filter(match__isnull=False)
        elif match_filter == 'without_match':
            images = images.filter(match__isnull=True)
        
        if category:
            images = images.filter(categories=category)
        elif not show_all and request.user.preferred_categories.exists():
            # Filtrar por preferencias solo si no hay filtro de categoría específico
            user_categories = request.user.preferred_categories.all()
            images = images.filter(categories__in=user_categories).distinct()
            
        if year:
            images = images.filter(year=year)
            
        if status_filter:
            images = images.filter(status=status_filter)
    else:
        # Si no hay filtros válidos, aplicar preferencias por defecto
        if not show_all and request.user.preferred_categories.exists():
            user_categories = request.user.preferred_categories.all()
            images = images.filter(categories__in=user_categories).distinct()
    
    # Agrupar imágenes por partido
    albums = []
    
    # Obtener imágenes con partido
    images_with_match = images.filter(match__isnull=False)
    
    # Agrupar por partido
    match_groups = {}
    for image in images_with_match:
        match_id = image.match.id
        if match_id not in match_groups:
            match_groups[match_id] = {
                'match': image.match,
                'images': [],
                'image_count': 0
            }
        match_groups[match_id]['images'].append(image)
        match_groups[match_id]['image_count'] += 1
    
    # Convertir a lista y ordenar por fecha del partido
    albums = list(match_groups.values())
    albums.sort(key=lambda x: x['match'].match_date, reverse=True)
    
    # Obtener imágenes sin partido
    images_without_match = images.filter(match__isnull=True)
    
    # Agrupar imágenes sin partido por album_group_id
    album_group_groups = {}
    single_images = []
    
    for image in images_without_match:
        if image.album_group_id:
            # Agrupar por album_group_id
            group_id = str(image.album_group_id)
            if group_id not in album_group_groups:
                album_group_groups[group_id] = {
                    'album_group_id': image.album_group_id,
                    'album_name': image.album_name or 'Álbum',
                    'images': [],
                    'image_count': 0,
                    'upload_date': image.upload_date  # Usar fecha de primera imagen para ordenar
                }
            album_group_groups[group_id]['images'].append(image)
            album_group_groups[group_id]['image_count'] += 1
            # Actualizar fecha si es más reciente (para ordenar por la más reciente)
            if image.upload_date > album_group_groups[group_id]['upload_date']:
                album_group_groups[group_id]['upload_date'] = image.upload_date
        else:
            # Imagen individual sin grupo
            single_images.append(image)
    
    # Convertir grupos de album_group_id a lista de álbumes
    album_groups = list(album_group_groups.values())
    album_groups.sort(key=lambda x: x['upload_date'], reverse=True)
    
    # Paginación para álbumes - mezclar álbumes de partidos, álbumes de grupos e imágenes individuales
    all_items = []
    
    # Agregar álbumes de partidos
    for album in albums:
        all_items.append({
            'type': 'album',
            'match': album['match'],
            'images': album['images'],
            'image_count': album['image_count']
        })
    
    # Agregar álbumes de grupos (sin partido)
    for album_group in album_groups:
        all_items.append({
            'type': 'album_group',
            'album_group_id': album_group['album_group_id'],
            'album_name': album_group['album_name'],
            'images': album_group['images'],
            'image_count': album_group['image_count'],
            'upload_date': album_group['upload_date']
        })
    
    # Agregar imágenes individuales
    for image in single_images:
        all_items.append({
            'type': 'single',
            'image': image,
            'image_count': 1
        })
    
    # Ordenar por fecha
    def get_sort_date(item):
        if item['type'] == 'album':
            return item['match'].match_date
        elif item['type'] == 'album_group':
            return item['upload_date']
        else:
            return item['image'].upload_date
    
    all_items.sort(key=get_sort_date, reverse=True)
    
    paginator = Paginator(all_items, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Estadísticas para la vista
    total_images = Image.objects.filter(status='approved').count()
    pending_images = Image.objects.filter(status='pending').count()
    total_albums = len(albums) + len(album_groups)  # Incluir álbumes de grupos
    total_single_images = len(single_images)
    
    # Obtener etiquetas populares para sugerencias
    popular_tags = []
    try:
        # Recopilar todas las etiquetas manuales
        manual_tags = []
        for image in Image.objects.filter(status='approved').exclude(tags=''):
            manual_tags.extend([tag.strip().lower() for tag in image.tags.split(',') if tag.strip()])
        
        # Recopilar etiquetas automáticas
        auto_tags = []
        for image in Image.objects.filter(status='approved').exclude(auto_tags=[]):
            if isinstance(image.auto_tags, list):
                auto_tags.extend([tag.lower() for tag in image.auto_tags])
        
        # Combinar y contar frecuencias
        from collections import Counter
        all_tags = manual_tags + auto_tags
        if all_tags:
            tag_counts = Counter(all_tags)
            popular_tags = [tag for tag, count in tag_counts.most_common(15)]
    except Exception as e:
        print(f"Error obteniendo etiquetas populares: {e}")
    
    context = {
        'page_obj': page_obj,
        'filter_form': filter_form,
        'total_images': total_images,
        'pending_images': pending_images,
        'total_albums': total_albums,
        'total_single_images': total_single_images,
        'popular_tags': popular_tags,
        'current_filters': request.GET.dict(),
        'show_all': show_all,
        'has_preferences': request.user.preferred_categories.exists(),
        'view_mode': 'albums',
    }
    
    return render(request, 'videos/image_gallery.html', context)


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def image_upload(request):
    """Vista para subir imágenes"""
    if request.method == 'POST':
        form = ImageUploadForm(request.POST, request.FILES)
        if form.is_valid():
            image = form.save(commit=False)
            image.uploaded_by = request.user
            
            # Procesar imagen (convertir HEIC si es necesario)
            try:
                uploaded_file = request.FILES.get('image')
                if uploaded_file:
                    processed_file, original_ext, was_converted = process_uploaded_image(uploaded_file)
                    
                    # Actualizar el archivo en la instancia
                    image.image = processed_file
                    image.original_format = original_ext.lstrip('.')
                    image.was_converted = was_converted
                    
                    if was_converted:
                        logger.info(f"Imagen convertida de {original_ext} a JPEG para usuario {request.user.username}")
                        
            except Exception as e:
                logger.error(f"Error procesando imagen: {str(e)}")
                messages.error(request, f'Error al procesar la imagen: {str(e)}')
                
                # Preparar recent_matches con la misma lógica
                club_query = (
                    Q(home_team__name__icontains=getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')) |
                    Q(away_team__name__icontains=getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')) |
                    Q(home_team_text__icontains=getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')) |
                    Q(away_team_text__icontains=getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP'))
                )
                now = timezone.now()
                past_matches = Match.objects.select_related(
                    'home_team', 'away_team', 'league'
                ).filter(club_query, match_date__lt=now).order_by('-match_date')[:10]
                next_match = Match.objects.select_related(
                    'home_team', 'away_team', 'league'
                ).filter(club_query, match_date__gte=now).order_by('match_date').first()
                
                if next_match:
                    recent_matches = list(past_matches) + [next_match]
                    recent_matches.sort(key=lambda x: x.match_date, reverse=True)
                else:
                    recent_matches = list(past_matches)
                
                return render(request, 'videos/image_upload.html', {
                    'form': form,
                    'recent_matches': recent_matches
                })
            
            # Si el usuario es superuser, aprobar directamente sin pasar por Vision API
            if request.user.is_superuser:
                image.status = 'approved'
                image.moderated_by = request.user
                image.moderation_date = timezone.now()
                image.moderation_notes = 'Aprobada automáticamente por superusuario'
                image.vision_api_checked = False
                image.vision_api_safe = True
                image.vision_api_details = {'skipped': 'Superuser approval - bypassed Vision API'}
                logger.info(f"Imagen aprobada automáticamente para superusuario {request.user.username}")
            # Procesar con Google Vision API si está habilitado
            elif getattr(settings, 'GOOGLE_VISION_ENABLED', False):
                try:
                    from .utils import check_image_with_vision_api, process_vision_tags_for_volleyball
                    
                    logger.info(f"Procesando imagen con Google Vision API para usuario {request.user.username}")
                    vision_result = check_image_with_vision_api(image.image, extract_labels=True, extract_text=True)
                    
                    image.vision_api_checked = True
                    image.vision_api_safe = vision_result.get('safe', False)
                    image.vision_api_details = vision_result
                    
                    # Procesar etiquetas automáticas si se detectaron
                    detected_labels = vision_result.get('labels', [])
                    detected_text = vision_result.get('text', '')
                    
                    if detected_labels or detected_text:
                        auto_tags = process_vision_tags_for_volleyball(detected_labels, detected_text)
                        # Establecer las etiquetas automáticas directamente
                        image.auto_tags = auto_tags
                        logger.info(f"Etiquetas detectadas: {auto_tags}")
                    
                    # Auto-aprobar SOLO si es segura, la API funcionó correctamente y la moderación automática está habilitada
                    if (vision_result.get('safe', False) and 
                        vision_result.get('details', {}).get('api_response_ok', False) and
                        getattr(settings, 'AUTO_MODERATION_ENABLED', False)):
                        image.status = 'approved'
                        image.moderated_by = request.user
                        image.moderation_date = timezone.now()
                        image.moderation_notes = 'Auto-aprobada por Google Vision API'
                        logger.info(f"Imagen auto-aprobada para usuario {request.user.username}")
                    else:
                        logger.info(f"Imagen requiere moderación manual (safe={vision_result.get('safe')}, auto_mod={getattr(settings, 'AUTO_MODERATION_ENABLED', False)})")
                        
                except Exception as e:
                    # Log error detallado y marcar como que requiere revisión manual
                    logger.error(
                        f"Error en Vision API al procesar imagen para usuario {request.user.username}: {str(e)}", 
                        exc_info=True,
                        extra={
                            'user': request.user.username,
                            'image_title': image.title if hasattr(image, 'title') else 'N/A'
                        }
                    )
                    
                    image.vision_api_checked = False
                    image.vision_api_safe = False
                    image.vision_api_details = {
                        'error': str(e), 
                        'api_response_ok': False,
                        'error_type': type(e).__name__
                    }
                    
                    # En desarrollo, mostrar el error al usuario
                    if settings.DEBUG:
                        messages.warning(
                            request, 
                            f'Error al procesar con Vision API: {str(e)}. La imagen quedará pendiente de moderación manual.'
                        )
                    
                    # En producción, enviar notificación a admins si está configurado
                    if not settings.DEBUG and settings.NOTIFICATION_EMAIL_ENABLED:
                        try:
                            from videosvoley.core.email_utils import send_notification_email
                            send_notification_email(
                                subject='Error en Google Vision API',
                                template_name='emails/vision_api_error.html',
                                context={
                                    'error': str(e),
                                    'user': request.user,
                                    'image_title': image.title if hasattr(image, 'title') else 'N/A',
                                },
                                recipient_list=settings.ADMIN_EMAIL_LIST
                            )
                        except Exception as email_error:
                            logger.error(f"Error al enviar notificación de error de Vision API: {email_error}")
            
            image.save()
            
            # Asignar categorías
            categories_to_add = []
            
            # Prioridad 1: Si hay match, usar categorías del partido
            if image.match:
                match = image.match
                if match.home_team and match.home_team.category:
                    categories_to_add.append(match.home_team.category)
                if match.away_team and match.away_team.category:
                    categories_to_add.append(match.away_team.category)
                if match.league:
                    categories_to_add.extend(list(match.league.categories.all()))
            
            # Prioridad 2: Si no hay match, usar categorías seleccionadas manualmente
            if not categories_to_add:
                category_ids = form.cleaned_data.get('categories', [])
                if category_ids:
                    categories_to_add = list(category_ids)
            
            # Asignar categorías (eliminar duplicados)
            if categories_to_add:
                # Convertir a set para eliminar duplicados, luego a list
                unique_categories = list(set(categories_to_add))
                image.categories.set(unique_categories)
            
            # Mensaje dinámico según el estado de la imagen
            if image.status == 'approved':
                auto_tags_msg = f" Se detectaron automáticamente las etiquetas: {', '.join(image.auto_tags[:3])}." if image.auto_tags else ""
                messages.success(request, f'Imagen subida y aprobada automáticamente.{auto_tags_msg}')
            else:
                auto_tags_msg = f" Se detectaron automáticamente las etiquetas: {', '.join(image.auto_tags[:3])}." if image.auto_tags else ""
                messages.success(request, f'Imagen subida correctamente. Está pendiente de moderación.{auto_tags_msg}')
            
            return redirect('videos:image_gallery')
        else:
            # El formulario no es válido, mostrar errores
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        # Pre-cargar partido si se pasa en la URL
        initial_data = {}
        match_id = request.GET.get('match')
        if match_id:
            try:
                match = Match.objects.get(id=match_id)
                initial_data['match'] = match
            except Match.DoesNotExist:
                pass
        
        form = ImageUploadForm(initial=initial_data)
    
    # Obtener partidos recientes para sugerir (solo pasados + el próximo)
    club_query = (
        Q(home_team__name__icontains=getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')) |
        Q(away_team__name__icontains=getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')) |
        Q(home_team_text__icontains=getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')) |
        Q(away_team_text__icontains=getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP'))
    )
    
    now = timezone.now()
    
    # Partidos del pasado (últimos 10)
    # (withdrawn excluidos automáticamente por el manager)
    past_matches = Match.objects.select_related(
        'home_team', 'away_team', 'league'
    ).filter(club_query, match_date__lt=now).order_by('-match_date')[:10]
    
    # Próximo partido futuro (solo uno)
    next_match = Match.objects.select_related(
        'home_team', 'away_team', 'league'
    ).filter(club_query, match_date__gte=now).order_by('match_date').first()
    
    # Combinar ambos querysets
    if next_match:
        # Convertir a lista para combinar y ordenar
        recent_matches = list(past_matches) + [next_match]
        recent_matches.sort(key=lambda x: x.match_date, reverse=True)
    else:
        recent_matches = list(past_matches)
    
    context = {
        'form': form,
        'recent_matches': recent_matches,
    }
    
    return render(request, 'videos/image_upload.html', context)


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def image_bulk_upload(request):
    """Vista para subir múltiples imágenes a la vez"""
    if request.method == 'POST':
        uploaded_files = request.FILES.getlist('images')
        
        if not uploaded_files:
            messages.error(request, 'No se seleccionaron imágenes.')
            return redirect('videos:image_bulk_upload')
        
        # Datos compartidos para todas las imágenes
        shared_data = {
            'uploaded_by': request.user,
            'image_type': request.POST.get('image_type', 'other'),
            'year': request.POST.get('year', timezone.now().year),
        }
        
        # Match y categorías opcionales compartidos
        match_id = request.POST.get('match')
        if match_id:
            try:
                shared_data['match'] = Match.objects.get(id=match_id)
            except Match.DoesNotExist:
                pass
        
        # Generar album_group_id y nombre
        import uuid
        from django.core.exceptions import ValidationError

        # Verificar si se está agregando a álbum existente
        existing_album_id = request.POST.get('existing_album_id')
        if existing_album_id and not match_id:
            try:
                album_uuid = uuid.UUID(existing_album_id)
                # Verificar que álbum existe
                existing_images = Image.objects.filter(album_group_id=album_uuid)
                if existing_images.exists():
                    album_group_id = album_uuid
                    album_name = existing_images.first().album_name or 'Álbum'
                    shared_data['album_group_id'] = album_group_id
                    shared_data['album_name'] = album_name
                else:
                    messages.error(request, 'El álbum especificado no existe.')
                    return redirect('videos:image_bulk_upload')
            except (ValueError, ValidationError):
                messages.error(request, 'ID de álbum inválido.')
                return redirect('videos:image_bulk_upload')
        else:
            # Código original: crear nuevo álbum si se marca
            create_album = request.POST.get('create_album') == 'on'
            album_name = request.POST.get('album_name', '').strip()
            if create_album and not match_id:
                if not album_name:
                    messages.error(request, 'El nombre del álbum es obligatorio cuando se agrupan imágenes.')
                    return redirect('videos:image_bulk_upload')
                album_group_id = uuid.uuid4()
                shared_data['album_group_id'] = album_group_id
                shared_data['album_name'] = album_name
        
        # Etiquetas compartidas
        shared_tags = request.POST.get('tags', '').strip()
        
        # Procesar cada imagen de forma optimizada
        success_count = 0
        errors = []
        
        # Detectar si es una petición móvil para optimizar procesamiento
        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
        is_mobile_request = any(mobile in user_agent for mobile in ['mobile', 'android', 'iphone', 'ipad'])
        
        for idx, uploaded_file in enumerate(uploaded_files):
            try:
                # Optimizar para móvil si es necesario
                processed_file, original_ext, was_converted = process_uploaded_image(
                    uploaded_file, 
                    optimize_for_mobile=is_mobile_request
                )
                
                # Obtener título y descripción individual
                title = request.POST.get(f'title_{idx}', uploaded_file.name.rsplit('.', 1)[0])
                description = request.POST.get(f'description_{idx}', '')
                
                # Validar archivo procesado
                if not processed_file.content_type.startswith('image/'):
                    errors.append(f'{uploaded_file.name}: No es una imagen válida')
                    continue
                
                if processed_file.size > 10 * 1024 * 1024:  # 10MB
                    errors.append(f'{uploaded_file.name}: Archivo demasiado grande (máx 10MB)')
                    continue
                
                # Crear imagen
                image = Image(
                    image=processed_file,
                    title=title,
                    description=description,
                    tags=shared_tags,
                    original_format=original_ext.lstrip('.'),
                    was_converted=was_converted,
                    **shared_data
                )
                
                if was_converted:
                    logger.info(f"Imagen {uploaded_file.name} convertida de {original_ext} a JPEG")
                
                # Si el usuario es superuser, aprobar directamente sin pasar por Vision API
                if request.user.is_superuser:
                    image.status = 'approved'
                    image.moderated_by = request.user
                    image.moderation_date = timezone.now()
                    image.moderation_notes = 'Aprobada automáticamente por superusuario'
                    image.vision_api_checked = False
                    image.vision_api_safe = True
                    image.vision_api_details = {'skipped': 'Superuser approval - bypassed Vision API'}
                    logger.info(f"Imagen aprobada automáticamente para superusuario {request.user.username}")
                # Procesar con Google Vision API si está habilitado (solo si no es móvil para mejor rendimiento)
                elif (getattr(settings, 'GOOGLE_VISION_ENABLED', False) and 
                    not is_mobile_request and 
                    len(uploaded_files) <= 5):  # Limitar Vision API en carga múltiple
                    try:
                        from .utils import check_image_with_vision_api, process_vision_tags_for_volleyball
                        
                        vision_result = check_image_with_vision_api(image.image, extract_labels=True, extract_text=True)
                        
                        image.vision_api_checked = True
                        image.vision_api_safe = vision_result.get('safe', False)
                        image.vision_api_details = vision_result
                        
                        # Procesar etiquetas automáticas
                        detected_labels = vision_result.get('labels', [])
                        detected_text = vision_result.get('text', '')
                        
                        if detected_labels or detected_text:
                            auto_tags = process_vision_tags_for_volleyball(detected_labels, detected_text)
                            image.auto_tags = auto_tags
                        
                        # Auto-aprobar si es segura
                        if (vision_result.get('safe', False) and 
                            vision_result.get('details', {}).get('api_response_ok', False) and
                            getattr(settings, 'AUTO_MODERATION_ENABLED', False)):
                            image.status = 'approved'
                            image.moderated_by = request.user
                            image.moderation_date = timezone.now()
                            image.moderation_notes = 'Auto-aprobada por Google Vision API'
                            
                    except Exception as e:
                        logger.error(f"Error en Vision API para {uploaded_file.name}: {str(e)}")
                        image.vision_api_checked = False
                        image.vision_api_safe = False
                        image.vision_api_details = {'error': str(e), 'api_response_ok': False}
                else:
                    # En móvil o carga múltiple, saltar Vision API para mejor rendimiento
                    image.vision_api_checked = False
                    image.vision_api_safe = True  # Asumir seguro para no bloquear
                    image.vision_api_details = {'skipped': 'Mobile or bulk upload optimization'}
                
                # Guardar imagen
                image.save()
                
                # Asignar categorías
                categories_to_add = []
                
                # Prioridad 1: Si hay match, usar categorías del partido
                if 'match' in shared_data and shared_data['match']:
                    match = shared_data['match']
                    if match.home_team and match.home_team.category:
                        categories_to_add.append(match.home_team.category)
                    if match.away_team and match.away_team.category:
                        categories_to_add.append(match.away_team.category)
                    if match.league:
                        categories_to_add.extend(list(match.league.categories.all()))
                
                # Prioridad 2: Si no hay match, usar categorías seleccionadas manualmente
                if not categories_to_add:
                    category_ids = request.POST.getlist('categories')
                    if category_ids:
                        categories_to_add = Category.objects.filter(id__in=category_ids)
                
                # Asignar categorías (eliminar duplicados)
                if categories_to_add:
                    # Convertir a set para eliminar duplicados, luego a list
                    unique_categories = list(set(categories_to_add))
                    image.categories.set(unique_categories)
                
                success_count += 1
                logger.info(f"Imagen subida exitosamente: {title} por {request.user.username}")
                
            except Exception as e:
                logger.error(f"Error procesando {uploaded_file.name}: {str(e)}")
                errors.append(f'{uploaded_file.name}: {str(e)}')
        
        # Mensajes de resultado
        if success_count > 0:
            messages.success(request, f'✅ {success_count} imagen(es) subida(s) correctamente.')
        
        if errors:
            for error in errors[:5]:  # Mostrar máximo 5 errores
                messages.warning(request, error)
            if len(errors) > 5:
                messages.warning(request, f'... y {len(errors) - 5} error(es) más.')
        
        if success_count > 0:
            # Redirigir al álbum si se agregaron fotos a uno existente
            existing_album_id = request.POST.get('existing_album_id')
            if existing_album_id:
                messages.success(
                    request,
                    f'✅ {success_count} imagen(es) agregada(s) al álbum correctamente.'
                )
                return redirect('videos:album_group_images', album_group_id=existing_album_id)
            else:
                return redirect('videos:image_gallery')
        else:
            return redirect('videos:image_bulk_upload')
    
    # GET request
    # Pre-cargar álbum existente si se proporciona en URL
    existing_album = None
    album_group_id_param = request.GET.get('album_group_id')
    if album_group_id_param:
        try:
            import uuid
            from django.core.exceptions import ValidationError

            # Validar formato UUID
            album_uuid = uuid.UUID(album_group_id_param)

            # Verificar que el álbum existe
            album_images = Image.objects.filter(
                album_group_id=album_uuid
            ).select_related('uploaded_by')

            if album_images.exists():
                first_image = album_images.first()
                existing_album = {
                    'album_group_id': str(album_uuid),
                    'album_name': first_image.album_name or 'Álbum',
                    'image_count': album_images.count(),
                    'upload_date': first_image.upload_date,
                }
        except (ValueError, ValidationError):
            # UUID inválido, ignorar
            pass

    # Pre-cargar partido si se pasa en la URL
    selected_match = None
    match_id = request.GET.get('match')
    if match_id:
        try:
            selected_match = Match.objects.get(id=match_id)
        except Match.DoesNotExist:
            pass
    
    # Obtener partidos recientes para sugerir (solo pasados + el próximo)
    club_query = (
        Q(home_team__name__icontains=getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')) |
        Q(away_team__name__icontains=getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')) |
        Q(home_team_text__icontains=getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')) |
        Q(away_team_text__icontains=getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP'))
    )
    
    now = timezone.now()
    
    # Partidos del pasado (últimos 10)
    # (withdrawn excluidos automáticamente por el manager)
    past_matches = Match.objects.select_related(
        'home_team', 'away_team', 'league'
    ).filter(club_query, match_date__lt=now).order_by('-match_date')[:10]
    
    # Próximo partido futuro (solo uno)
    next_match = Match.objects.select_related(
        'home_team', 'away_team', 'league'
    ).filter(club_query, match_date__gte=now).order_by('match_date').first()
    
    # Combinar ambos querysets
    if next_match:
        # Convertir a lista para combinar y ordenar
        recent_matches = list(past_matches) + [next_match]
        recent_matches.sort(key=lambda x: x.match_date, reverse=True)
    else:
        recent_matches = list(past_matches)
    
    # Obtener categorías activas
    categories = Category.objects.filter(is_active=True).order_by('name')
    
    # Tipos de imagen
    image_types = Image.IMAGE_TYPES
    
    context = {
        'recent_matches': recent_matches,
        'categories': categories,
        'image_types': image_types,
        'current_year': timezone.now().year,
        'selected_match': selected_match,
        'existing_album': existing_album,
    }

    return render(request, 'videos/image_bulk_upload.html', context)


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def image_detail(request, image_id):
    """Vista de detalle de imagen"""
    image = get_object_or_404(
        Image.objects.select_related(
            'match__home_team', 'match__away_team', 'match__league',
            'uploaded_by', 'moderated_by'
        ).prefetch_related('categories'),
        id=image_id
    )
    
    # Solo mostrar imágenes aprobadas a usuarios normales
    if not request.user.is_staff and image.status != 'approved':
        messages.error(request, 'Imagen no disponible.')
        return redirect('videos:image_gallery')
    
    # Imágenes relacionadas del mismo partido
    related_images = Image.objects.filter(
        match=image.match,
        status='approved'
    ).exclude(id=image.id)[:6]
    
    context = {
        'image': image,
        'related_images': related_images,
    }
    
    return render(request, 'videos/image_detail.html', context)


@login_required
@user_passes_test(lambda u: u.is_staff, login_url='/')
def image_moderation(request):
    """Vista de moderación para admins"""
    images = Image.objects.select_related(
        'match__home_team', 'match__away_team', 'match__league',
        'uploaded_by'
    ).prefetch_related('categories').filter(status='pending').order_by('upload_date')
    
    # Paginación
    paginator = Paginator(images, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'pending_count': images.count(),
    }
    
    return render(request, 'videos/image_moderation.html', context)


@login_required
@user_passes_test(lambda u: u.is_staff, login_url='/')
def image_moderate_action(request, image_id):
    """Acción de moderación individual"""
    image = get_object_or_404(Image, id=image_id, status='pending')
    
    if request.method == 'POST':
        form = ImageModerationForm(request.POST, instance=image)
        if form.is_valid():
            action = form.cleaned_data['action']
            notes = form.cleaned_data['moderation_notes']
            
            image.moderate(
                moderator=request.user,
                approved=(action == 'approve'),
                notes=notes
            )
            
            action_text = 'aprobada' if action == 'approve' else 'rechazada'
            messages.success(request, f'Imagen {action_text} correctamente.')
            return redirect('videos:image_moderation')
    else:
        form = ImageModerationForm()
    
    context = {
        'image': image,
        'form': form,
    }
    
    return render(request, 'videos/image_moderate.html', context)


@login_required
@user_passes_test(lambda u: u.is_staff, login_url='/')
def image_moderate_bulk(request):
    """Moderación masiva de imágenes"""
    if request.method == 'POST':
        action = request.POST.get('action')
        image_ids = request.POST.getlist('image_ids')
        notes = request.POST.get('notes', '')
        
        if action in ['approve', 'reject'] and image_ids:
            images = Image.objects.filter(id__in=image_ids, status='pending')
            approved = (action == 'approve')
            
            for image in images:
                image.moderate(
                    moderator=request.user,
                    approved=approved,
                    notes=notes
                )
            
            action_text = 'aprobadas' if approved else 'rechazadas'
            messages.success(request, f'{images.count()} imágenes {action_text}.')
        
        return redirect('videos:image_moderation')
    
    return redirect('videos:image_moderation')


def match_images(request, match_id):
    """Vista de imágenes de un partido específico"""
    match = get_object_or_404(
        Match.objects.select_related('home_team', 'away_team', 'league'),
        id=match_id
    )
    
    images = Image.objects.filter(
        match=match,
        status='approved'
    ).select_related('uploaded_by').order_by('-upload_date')
    
    # Paginación
    paginator = Paginator(images, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'match': match,
        'page_obj': page_obj,
        'all_images': images,
        'total_images': images.count(),
    }

    return render(request, 'videos/match_images.html', context)


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def album_group_images(request, album_group_id):
    """Vista de imágenes de un álbum de grupo (sin partido)"""
    # album_group_id ya viene como UUID desde la URL (gracias al path converter <uuid:album_group_id>)
    images = Image.objects.filter(
        album_group_id=album_group_id,
        status='approved'
    ).select_related('uploaded_by').prefetch_related('categories').order_by('-upload_date')
    
    if not images.exists():
        raise Http404("Álbum no encontrado")
    
    # Obtener información del álbum desde la primera imagen
    first_image = images.first()
    
    # Paginación
    paginator = Paginator(images, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Preparar información del álbum
    album_info = {
        'album_group_id': album_group_id,
        'album_name': first_image.album_name or 'Álbum',
        'image_count': images.count(),
        'upload_date': first_image.upload_date,
        'categories': first_image.categories.all(),
        'image_type': first_image.get_image_type_display(),
    }
    
    context = {
        'album': album_info,
        'page_obj': page_obj,
        'all_images': images,
        'total_images': images.count(),
    }

    return render(request, 'videos/album_group_images.html', context)


def about(request):
    """Vista de la página Quiénes somos"""
    return render(request, 'videos/about.html')


# ===============================
# VISTAS DE NOTIFICACIONES Y MODERACIÓN
# ===============================

@login_required
@user_passes_test(lambda u: u.is_superuser, login_url='/')
def moderation_counts_api(request):
    """API para obtener contadores de elementos pendientes de moderación"""
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    
    # Contar usuarios pendientes de aprobación
    pending_users_count = User.objects.filter(is_approved=False).count()
    
    # Contar imágenes pendientes de moderación
    pending_images_count = Image.objects.filter(status='pending').count()
    
    # Total de elementos pendientes
    total_pending = pending_users_count + pending_images_count
    
    return JsonResponse({
        'success': True,
        'pending_users': pending_users_count,
        'pending_images': pending_images_count,
        'total_pending': total_pending
    })


@login_required
@user_passes_test(lambda u: u.is_superuser, login_url='/')
def moderation_panel(request):
    """Panel de moderación simplificado para superusers"""
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    
    # Obtener usuarios pendientes de aprobación
    pending_users = User.objects.filter(is_approved=False).order_by('date_joined')
    
    # Obtener imágenes pendientes de moderación
    pending_images = Image.objects.filter(status='pending').select_related(
        'uploaded_by', 'match__home_team', 'match__away_team', 'match__league'
    ).prefetch_related('categories').order_by('upload_date')
    
    context = {
        'pending_users': pending_users,
        'pending_images': pending_images,
        'pending_users_count': pending_users.count(),
        'pending_images_count': pending_images.count(),
    }
    
    return render(request, 'videos/moderation_panel.html', context)


@login_required
@user_passes_test(lambda u: u.is_superuser, login_url='/')
@require_POST
def approve_user_api(request, user_id):
    """API para aprobar un usuario vía AJAX"""
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    
    try:
        user = User.objects.get(id=user_id, is_approved=False)
        user.is_approved = True
        user.is_active = True  # Asegurarse de que el usuario esté activo al aprobar
        user.save(update_fields=['is_approved', 'is_active'])
        
        # Enviar email de confirmación si está configurado
        if getattr(settings, 'NOTIFICATION_EMAIL_ENABLED', False):
            try:
                from videosvoley.core.email_utils import send_notification_email
                send_notification_email(
                    subject=f'Usuario aprobado - {user.username}',
                    template_name='emails/user_approved.html',
                    context={'user': user},
                    recipient_list=[user.email] if user.email else []
                )
            except Exception as e:
                logger.warning(f"Error enviando email de aprobación: {e}")
        
        return JsonResponse({
            'success': True,
            'message': f'Usuario {user.username} aprobado correctamente',
            'user_name': user.username
        })
        
    except User.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Usuario no encontrado o ya aprobado'
        }, status=404)
    except Exception as e:
        logger.error(f"Error aprobando usuario {user_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Error interno del servidor'
        }, status=500)


@login_required
@user_passes_test(lambda u: u.is_superuser, login_url='/')
@require_POST
def reject_user_api(request, user_id):
    """API para rechazar un usuario vía AJAX"""
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    
    try:
        user = User.objects.get(id=user_id, is_approved=False)
        # Rechazar = desactivar el usuario y mantener is_approved en False
        user.is_active = False
        user.save(update_fields=['is_active'])
        
        # Enviar email de rechazo si está configurado
        if getattr(settings, 'NOTIFICATION_EMAIL_ENABLED', False):
            try:
                from videosvoley.core.email_utils import send_notification_email
                send_notification_email(
                    subject=f'Actualización de tu solicitud en I Love Voley',
                    template_name='emails/user_rejected.html',
                    context={
                        'user': user,
                        'site_name': 'I Love Voley',
                    },
                    recipient_list=[user.email] if user.email else []
                )
            except Exception as e:
                logger.warning(f"Error enviando email de rechazo: {e}")
        
        return JsonResponse({
            'success': True,
            'message': f'Usuario {user.username} rechazado correctamente',
            'user_name': user.username
        })
        
    except User.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Usuario no encontrado o ya procesado'
        }, status=404)
    except Exception as e:
        logger.error(f"Error rechazando usuario {user_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Error interno del servidor'
        }, status=500)


@login_required
@user_passes_test(lambda u: u.is_superuser, login_url='/')
@require_POST
def moderate_image_api(request, image_id):
    """API para moderar una imagen vía AJAX"""
    try:
        image = Image.objects.get(id=image_id, status='pending')
        action = request.POST.get('action')  # 'approve' o 'reject'
        notes = request.POST.get('notes', '')
        
        if action not in ['approve', 'reject']:
            return JsonResponse({
                'success': False,
                'error': 'Acción no válida'
            }, status=400)
        
        # Usar el método existente de moderación
        approved = (action == 'approve')
        image.moderate(
            moderator=request.user,
            approved=approved,
            notes=notes
        )
        
        action_text = 'aprobada' if approved else 'rechazada'
        
        return JsonResponse({
            'success': True,
            'message': f'Imagen "{image.title}" {action_text} correctamente',
            'image_title': image.title,
            'action': action
        })
        
    except Image.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Imagen no encontrada o ya moderada'
        }, status=404)
    except Exception as e:
        logger.error(f"Error moderando imagen {image_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Error interno del servidor'
        }, status=500)


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
                from .models import Club
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



# ===============================
# VISTAS DE PLANTILLAS (PLAYERS Y STAFF)  
# ===============================

@login_required
@user_passes_test(user_is_approved, login_url="/pending-approval/")
def team_list(request):
    """Lista de equipos del club con información de plantillas"""
    # Configuración del club - usar solo CLUB_TEAM_NAME para máxima flexibilidad
    club_name = getattr(settings, "CLUB_TEAM_NAME", "SANT JOSEP")
    
    # Obtener categorías del usuario para filtrar
    user_categories = request.user.preferred_categories.all() if request.user.preferred_categories.exists() else Category.objects.filter(is_active=True)
    
    # Query base para equipos del club - filtrar por nombre que contenga CLUB_TEAM_NAME
    teams_query = Team.objects.select_related("category", "club").prefetch_related(
        "players", "staff"
    ).filter(is_active=True, name__icontains=club_name)
    
    # Filtrar por categorías preferidas del usuario
    category_filter = request.GET.get("category")
    show_all = request.GET.get("show_all", "0") == "1"
    
    if not show_all and not category_filter:
        teams_query = teams_query.filter(category__in=user_categories)
    elif category_filter:
        teams_query = teams_query.filter(category_id=category_filter)
    
    # Ordenar por categoría y nombre
    teams = teams_query.order_by("category__name", "name")
    
    # Añadir contadores de plantilla usando nueva estructura Person-Role
    for team in teams:
        team.active_players_count = team.player_roles.filter(is_active=True).count()
        team.active_staff_count = team.staff_roles.filter(is_active=True).count()
    
    # Obtener categorías para el filtro
    categories = Category.objects.filter(is_active=True).order_by("name")
    
    context = {
        "teams": teams,
        "categories": categories,
        "selected_category": category_filter,
        "show_all": show_all,
        "user_categories": user_categories,
    }
    
    return render(request, "videos/team_list.html", context)


@login_required
@user_passes_test(user_is_approved, login_url="/pending-approval/")
def team_roster(request, team_id):
    """Vista de plantilla de un equipo específico"""
    team = get_object_or_404(
        Team.objects.select_related("category", "club"),
        id=team_id
    )
    
    # Verificar que sea un equipo del club - usar solo CLUB_TEAM_NAME
    club_name = getattr(settings, "CLUB_TEAM_NAME", "SANT JOSEP")
    
    is_club_team = club_name.lower() in team.name.lower()
    
    if not is_club_team:
        messages.error(request, "Este equipo no pertenece al club.")
        return redirect("videos:team_list")
    
    # Obtener jugadores activos ordenados por número de dorsal usando nueva estructura
    player_roles = team.player_roles.filter(is_active=True).select_related('person').order_by("jersey_number", "person__last_name", "person__first_name")
    
    # Obtener staff activo ordenado por rol usando nueva estructura
    staff_roles = team.staff_roles.filter(is_active=True).select_related('person').order_by("role", "person__last_name", "person__first_name")
    
    # Filtros opcionales
    position_filter = request.GET.get("position")
    if position_filter:
        player_roles = player_roles.filter(position=position_filter)
    
    role_filter = request.GET.get("role")
    if role_filter:
        staff_roles = staff_roles.filter(role=role_filter)
    
    # Estadísticas de la plantilla usando nueva estructura
    stats = {
        "total_players": player_roles.count(),
        "total_staff": staff_roles.count(),
        "players_with_jersey": 0,
        "positions_covered": 0,
        "positions_distribution": {},
        "roles_distribution": {},
    }
    
    # Contar jugadores con dorsal asignado
    stats["players_with_jersey"] = player_roles.filter(jersey_number__isnull=False).count()
    
    # Contar posiciones cubiertas (que tienen al menos un jugador)
    positions_with_players = set()
    for player_role in player_roles:
        if player_role.position:
            positions_with_players.add(player_role.position)
    stats["positions_covered"] = len(positions_with_players)
    
    # Distribución por posiciones
    for player_role in player_roles:
        pos = player_role.get_position_display() if player_role.position else "Sin asignar"
        stats["positions_distribution"][pos] = stats["positions_distribution"].get(pos, 0) + 1
    
    # Distribución por roles del staff
    for staff_role in staff_roles:
        role = staff_role.get_role_display()
        stats["roles_distribution"][role] = stats["roles_distribution"].get(role, 0) + 1
    
    # Opciones para filtros - usar las opciones de los nuevos modelos
    from .models import PlayerRole, StaffRole
    position_choices = PlayerRole.POSITION_CHOICES
    role_choices = StaffRole.STAFF_ROLES
    
    context = {
        "team": team,
        "player_roles": player_roles,
        "staff_roles": staff_roles,
        "stats": stats,
        "position_choices": position_choices,
        "role_choices": role_choices,
        "selected_position": position_filter,
        "selected_role": role_filter,
    }
    
    return render(request, "videos/team_roster.html", context)


@login_required
@user_passes_test(user_is_approved, login_url="/pending-approval/")
def roster_overview(request):
    """Vista general de todas las plantillas del club"""
    # Configuración del club - usar solo CLUB_TEAM_NAME para máxima flexibilidad
    club_name = getattr(settings, "CLUB_TEAM_NAME", "SANT JOSEP")
    
    # Obtener categorías del usuario para filtrar
    user_categories = request.user.preferred_categories.all() if request.user.preferred_categories.exists() else Category.objects.filter(is_active=True)
    
    # Query base para equipos del club - filtrar por nombre que contenga CLUB_TEAM_NAME
    teams_query = Team.objects.select_related("category", "club").prefetch_related(
        "players__user", "staff__user"
    ).filter(is_active=True, name__icontains=club_name)
    
    # Filtrar por categorías preferidas del usuario
    category_filter = request.GET.get("category")
    show_all = request.GET.get("show_all", "0") == "1"
    
    if not show_all and not category_filter:
        teams_query = teams_query.filter(category__in=user_categories)
    elif category_filter:
        teams_query = teams_query.filter(category_id=category_filter)
    
    teams = teams_query.order_by("category__name", "name")
    
    # Estadísticas generales
    total_stats = {
        "total_teams": teams.count(),
        "total_players": 0,
        "total_staff": 0,
        "teams_with_good_roster": 0,  # Equipos con 8+ jugadores (buen número para rotaciones)
        "categories_summary": {},
    }
    
    for team in teams:
        # Usar nueva estructura Person-Role
        active_player_roles = team.player_roles.filter(is_active=True)
        active_staff_roles = team.staff_roles.filter(is_active=True)
        
        team.active_players_count = active_player_roles.count()
        team.active_staff_count = active_staff_roles.count()
        team.has_good_roster = team.active_players_count >= 8  # Suficientes para rotaciones
        
        total_stats["total_players"] += team.active_players_count
        total_stats["total_staff"] += team.active_staff_count
        
        if team.has_good_roster:
            total_stats["teams_with_good_roster"] += 1
        
        # Estadísticas por categoría
        cat_name = team.category.name if team.category else "Sin categoría"
        if cat_name not in total_stats["categories_summary"]:
            total_stats["categories_summary"][cat_name] = {
                "teams": 0, "players": 0, "staff": 0
            }
        
        total_stats["categories_summary"][cat_name]["teams"] += 1
        total_stats["categories_summary"][cat_name]["players"] += team.active_players_count
        total_stats["categories_summary"][cat_name]["staff"] += team.active_staff_count
    
    # Obtener categorías para el filtro
    categories = Category.objects.filter(is_active=True).order_by("name")
    
    context = {
        "teams": teams,
        "total_stats": total_stats,
        "categories": categories,
        "selected_category": category_filter,
        "show_all": show_all,
        "user_categories": user_categories,
    }
    
    return render(request, "videos/roster_overview.html", context)


# =============================================================================
# VISTAS PARA GESTIÓN DE PERSONAS (Person-Role)
# =============================================================================

@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def person_list(request):
    """Vista de listado de personas del club"""
    # Obtener todas las personas activas con sus roles
    people = Person.objects.filter(is_active=True).prefetch_related(
        'player_roles__team__category',
        'staff_roles__team__category'
    ).order_by('last_name', 'first_name')
    
    # Filtros
    search = request.GET.get('search', '').strip()
    role_type = request.GET.get('role_type', '')  # 'player', 'staff', o ''
    
    if search:
        people = people.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search)
        )
    
    if role_type == 'player':
        people = people.filter(player_roles__is_active=True).distinct()
    elif role_type == 'staff':
        people = people.filter(staff_roles__is_active=True).distinct()
    
    # Paginación
    paginator = Paginator(people, 24)  # 24 personas por página
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Enriquecer con info de roles
    for person in page_obj:
        person.active_player_roles = person.get_player_roles()
        person.active_staff_roles = person.get_staff_roles()
    
    context = {
        'page_obj': page_obj,
        'search': search,
        'role_type': role_type,
    }
    
    return render(request, 'videos/person_list.html', context)


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def person_detail(request, person_id):
    """Vista de detalle de una persona"""
    person = get_object_or_404(
        Person.objects.prefetch_related(
            'player_roles__team__category',
            'staff_roles__team__category'
        ),
        id=person_id
    )
    
    # Obtener roles activos e inactivos
    player_roles = person.player_roles.select_related('team__category').order_by('-is_active', 'team__name')
    staff_roles = person.staff_roles.select_related('team__category').order_by('-is_active', 'team__name')
    
    # Verificar permisos de edición
    can_edit = request.user.can_edit_person(person)
    
    context = {
        'person': person,
        'player_roles': player_roles,
        'staff_roles': staff_roles,
        'can_edit': can_edit,
    }
    
    return render(request, 'videos/person_detail.html', context)


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def person_create(request):
    """Vista para crear una nueva persona"""
    if request.method == 'POST':
        form = PersonForm(request.POST, request.FILES)
        
        if form.is_valid():
            person = form.save(commit=False)
            
            # Procesar imagen recortada si está presente
            cropped_photo_data = request.POST.get('cropped_photo_data')
            if cropped_photo_data and cropped_photo_data.startswith('data:image'):
                try:
                    # Extraer datos base64
                    format_str, imgstr = cropped_photo_data.split(';base64,')
                    ext = format_str.split('/')[-1]
                    
                    # Decodificar imagen
                    data = base64.b64decode(imgstr)
                    
                    # Crear archivo temporal
                    filename = f"person_{uuid.uuid4().hex[:8]}.{ext}"
                    photo_file = ContentFile(data, name=filename)
                    
                    # Asignar la foto recortada
                    person.photo = photo_file
                    
                except Exception as e:
                    logger.error(f'Error al procesar la imagen recortada: {str(e)}')
                    messages.error(request, f'Error al procesar la imagen recortada: {str(e)}')
                    return render(request, 'videos/person_form.html', {
                        'form': form,
                        'title': 'Agregar Nueva Persona',
                        'submit_text': 'Crear Persona',
                    })
            
            # Si el usuario no tiene un person vinculado, vincular este
            if not hasattr(request.user, 'person'):
                person.user = request.user
            
            person.save()
            messages.success(request, f'¡Persona creada exitosamente! Ahora puedes agregar roles de jugador o staff.')
            return redirect('videos:person_detail', person_id=person.id)
    else:
        form = PersonForm()
    
    context = {
        'form': form,
        'title': 'Agregar Nueva Persona',
        'submit_text': 'Crear Persona',
    }
    
    return render(request, 'videos/person_form.html', context)


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def person_edit(request, person_id):
    """Vista para editar una persona existente"""
    person = get_object_or_404(Person, id=person_id)
    
    # Verificar permisos
    can_edit = request.user.can_edit_person(person)
    
    if not can_edit:
        messages.error(request, 'No tienes permisos para editar esta persona.')
        return redirect('videos:person_detail', person_id=person.id)
    
    if request.method == 'POST':
        form = PersonForm(request.POST, request.FILES, instance=person)
        
        if form.is_valid():
            # Procesar imagen recortada si está presente
            cropped_photo_data = request.POST.get('cropped_photo_data')
            if cropped_photo_data and cropped_photo_data.startswith('data:image'):
                try:
                    # Extraer datos base64
                    format_str, imgstr = cropped_photo_data.split(';base64,')
                    ext = format_str.split('/')[-1]
                    
                    # Decodificar imagen
                    data = base64.b64decode(imgstr)
                    
                    # Crear archivo
                    filename = f"person_{person.id}_{uuid.uuid4().hex[:8]}.{ext}"
                    photo_file = ContentFile(data, name=filename)
                    
                    # Asignar la imagen recortada al person
                    person.photo = photo_file
                    
                except Exception as e:
                    logger.error(f'Error al procesar la imagen recortada: {str(e)}')
                    messages.error(request, f'Error al procesar la imagen recortada: {str(e)}')
                    return render(request, 'videos/person_form.html', {
                        'form': form,
                        'person': person,
                        'title': f'Editar {person.full_name}',
                        'submit_text': 'Guardar Cambios',
                    })
            
            form.save()
            messages.success(request, '¡Información actualizada correctamente!')
            return redirect('videos:person_detail', person_id=person.id)
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = PersonForm(instance=person)
    
    context = {
        'form': form,
        'person': person,
        'title': f'Editar {person.full_name}',
        'submit_text': 'Guardar Cambios',
    }
    
    return render(request, 'videos/person_form.html', context)


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def player_role_create(request, person_id):
    """Vista para agregar un rol de jugador a una persona"""
    person = get_object_or_404(Person, id=person_id)
    
    # Verificar permisos
    can_edit = request.user.is_staff or request.user == person.user
    if not can_edit:
        messages.error(request, 'No tienes permisos para agregar roles a esta persona.')
        return redirect('videos:person_detail', person_id=person.id)
    
    if request.method == 'POST':
        form = PlayerRoleForm(request.POST, person=person)
        if form.is_valid():
            player_role = form.save(commit=False)
            player_role.person = person
            player_role.save()
            messages.success(request, f'¡Rol de jugador agregado en {player_role.team.name}!')
            return redirect('videos:person_detail', person_id=person.id)
    else:
        form = PlayerRoleForm(person=person)
    
    context = {
        'form': form,
        'person': person,
        'title': f'Agregar Rol de Jugador - {person.full_name}',
        'submit_text': 'Agregar Rol',
        'role_type': 'player',
    }
    
    return render(request, 'videos/role_form.html', context)


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def staff_role_create(request, person_id):
    """Vista para agregar un rol de staff a una persona"""
    person = get_object_or_404(Person, id=person_id)
    
    # Verificar permisos
    can_edit = request.user.is_staff or request.user == person.user
    if not can_edit:
        messages.error(request, 'No tienes permisos para agregar roles a esta persona.')
        return redirect('videos:person_detail', person_id=person.id)
    
    if request.method == 'POST':
        form = StaffRoleForm(request.POST, person=person)
        if form.is_valid():
            staff_role = form.save(commit=False)
            staff_role.person = person
            staff_role.save()
            messages.success(request, f'¡Rol de staff agregado en {staff_role.team.name}!')
            return redirect('videos:person_detail', person_id=person.id)
    else:
        form = StaffRoleForm(person=person)
    
    context = {
        'form': form,
        'person': person,
        'title': f'Agregar Rol de Staff - {person.full_name}',
        'submit_text': 'Agregar Rol',
        'role_type': 'staff',
    }
    
    return render(request, 'videos/role_form.html', context)


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def player_role_edit(request, role_id):
    """Vista para editar un rol de jugador"""
    player_role = get_object_or_404(PlayerRole.objects.select_related('person', 'team'), id=role_id)
    
    # Verificar permisos
    can_edit = request.user.is_staff or request.user == player_role.person.user
    if not can_edit:
        messages.error(request, 'No tienes permisos para editar este rol.')
        return redirect('videos:person_detail', person_id=player_role.person.id)
    
    if request.method == 'POST':
        form = PlayerRoleForm(request.POST, instance=player_role, person=player_role.person)
        if form.is_valid():
            form.save()
            messages.success(request, '¡Rol actualizado correctamente!')
            return redirect('videos:person_detail', person_id=player_role.person.id)
    else:
        form = PlayerRoleForm(instance=player_role, person=player_role.person)
    
    context = {
        'form': form,
        'person': player_role.person,
        'player_role': player_role,
        'title': f'Editar Rol de Jugador - {player_role.person.full_name}',
        'submit_text': 'Guardar Cambios',
        'role_type': 'player',
    }
    
    return render(request, 'videos/role_form.html', context)


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def staff_role_edit(request, role_id):
    """Vista para editar un rol de staff"""
    staff_role = get_object_or_404(StaffRole.objects.select_related('person', 'team'), id=role_id)
    
    # Verificar permisos
    can_edit = request.user.is_staff or request.user == staff_role.person.user
    if not can_edit:
        messages.error(request, 'No tienes permisos para editar este rol.')
        return redirect('videos:person_detail', person_id=staff_role.person.id)
    
    if request.method == 'POST':
        form = StaffRoleForm(request.POST, instance=staff_role, person=staff_role.person)
        if form.is_valid():
            form.save()
            messages.success(request, '¡Rol actualizado correctamente!')
            return redirect('videos:person_detail', person_id=staff_role.person.id)
    else:
        form = StaffRoleForm(instance=staff_role, person=staff_role.person)
    
    context = {
        'form': form,
        'person': staff_role.person,
        'staff_role': staff_role,
        'title': f'Editar Rol de Staff - {staff_role.person.full_name}',
        'submit_text': 'Guardar Cambios',
        'role_type': 'staff',
    }
    
    return render(request, 'videos/role_form.html', context)


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
@require_POST
def player_role_toggle_active(request, role_id):
    """Vista AJAX para activar/desactivar rol de jugador"""
    player_role = get_object_or_404(PlayerRole, id=role_id)
    
    # Verificar permisos
    can_edit = request.user.is_staff or request.user == player_role.person.user
    if not can_edit:
        return JsonResponse({'success': False, 'error': 'Sin permisos'}, status=403)
    
    player_role.is_active = not player_role.is_active
    player_role.save()
    
    status = 'activado' if player_role.is_active else 'desactivado'
    messages.success(request, f'Rol de jugador {status} correctamente.')
    
    return JsonResponse({'success': True, 'is_active': player_role.is_active})


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
@require_POST
def staff_role_toggle_active(request, role_id):
    """Vista AJAX para activar/desactivar rol de staff"""
    staff_role = get_object_or_404(StaffRole, id=role_id)
    
    # Verificar permisos
    can_edit = request.user.is_staff or request.user == staff_role.person.user
    if not can_edit:
        return JsonResponse({'success': False, 'error': 'Sin permisos'}, status=403)
    
    staff_role.is_active = not staff_role.is_active
    staff_role.save()
    
    status = 'activado' if staff_role.is_active else 'desactivado'
    messages.success(request, f'Rol de staff {status} correctamente.')
    
    return JsonResponse({'success': True, 'is_active': staff_role.is_active})

