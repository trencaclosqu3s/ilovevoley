from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.contrib.postgres.search import TrigramSimilarity
from django.http import JsonResponse
from django.conf import settings
from unidecode import unidecode
from datetime import datetime, timedelta
import calendar
from django.utils import timezone
from .models import Video, Comment, Category, League, Match, Team, Standing
from .forms import VideoForm, CommentForm


def user_is_approved(user):
    """Verifica si el usuario está aprobado para acceder al contenido"""
    return user.is_approved


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def video_list(request):
    videos = Video.objects.select_related('category', 'created_by', 'match__home_team', 'match__away_team', 'match__league').prefetch_related('comments').all()
    categories = Category.objects.filter(is_active=True)
    leagues = League.objects.filter(is_active=True)
    teams = Team.objects.all()
    
    # Filtros
    category_filter = request.GET.get('category')
    league_filter = request.GET.get('league')
    team_filter = request.GET.get('team')
    search_query = request.GET.get('search', '').strip()
    
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
            Q(match__away_team__name__icontains=search_query)
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
        'can_add': can_add
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
            return redirect('video_list')
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
    leagues = League.objects.filter(is_active=True).prefetch_related('matches__videos')
    
    return render(request, 'videos/league_list.html', {
        'leagues': leagues
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
    
    # Obtener jornadas disponibles
    available_rounds = matches.values_list('round_number', flat=True).distinct().order_by('round_number')
    
    # Paginación de partidos
    paginator = Paginator(matches, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'videos/league_detail.html', {
        'league': league,
        'page_obj': page_obj,
        'standings': standings,
        'available_rounds': available_rounds,
        'selected_round': round_filter
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
    
    return render(request, 'videos/match_detail.html', {
        'match': match,
        'videos': videos
    })


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def calendar_view(request):
    """Vista del calendario de partidos"""
    # Configuración del club
    CLUB_TEAM_NAME = 'SANT JOSEP'
    
    # Obtener filtros
    show_all_teams = request.GET.get('all_teams', '0') == '1'
    league_filter = request.GET.get('league')
    category_filter = request.GET.get('category')
    
    # Consulta base de partidos
    matches = Match.objects.select_related(
        'home_team', 'away_team', 'league', 'league__category'
    ).order_by('match_date')
    
    # Filtrar por equipo del club por defecto
    if not show_all_teams:
        matches = matches.filter(
            Q(home_team__name__icontains=CLUB_TEAM_NAME) | 
            Q(away_team__name__icontains=CLUB_TEAM_NAME)
        )
    
    # Aplicar filtro de liga
    if league_filter:
        matches = matches.filter(league_id=league_filter)
    
    # Aplicar filtro de categoría
    if category_filter:
        matches = matches.filter(league__category_id=category_filter)
    
    # Obtener datos para filtros
    leagues = League.objects.filter(is_active=True).order_by('name')
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
        'club_team_name': CLUB_TEAM_NAME,
        'current_month': start_date,
        'prev_month': prev_month,
        'next_month': next_month,
        'year': year,
        'month': month,
        'calendar_weeks': calendar_weeks,
        'view_mode': view_mode,
        'month_name': month_names_es[month],
    })


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def standings_view(request):
    """Vista de clasificación de las ligas"""
    # Obtener filtros
    league_filter = request.GET.get('league')
    category_filter = request.GET.get('category')
    
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
    leagues = League.objects.filter(is_active=True).order_by('name')
    categories = Category.objects.filter(is_active=True).order_by('name')
    
    return render(request, 'videos/standings.html', {
        'standings_by_league': standings_by_league,
        'leagues': leagues,
        'categories': categories,
        'selected_league': league_filter,
        'selected_category': category_filter,
        'club_team_name': CLUB_TEAM_NAME,
    })


@login_required
def ajax_matches_by_category(request):
    """Vista AJAX para obtener partidos filtrados por categoría"""
    category_id = request.GET.get('category_id')
    club_team_name = getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')
    
    # Construir query base para equipos del club
    club_query = (Q(home_team__name__icontains=club_team_name) | 
                 Q(away_team__name__icontains=club_team_name))
    
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
            'text': f"{match.home_team.name} vs {match.away_team.name} - {match.match_date.strftime('%d/%m/%Y')} ({match.league.name})"
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
