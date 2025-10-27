"""
Views para la gestión de equipos y clubs.
Migradas desde videos.views para la nueva app teams.
"""
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Q, Prefetch
from django.http import JsonResponse
from django.conf import settings
from django.views.decorators.http import require_POST
from django.utils import timezone
from datetime import datetime, timedelta
import logging

from .models import Team, Club
from .forms import TeamForm, ClubForm

# Importar modelos de otras apps
from videosvoley.content.models import Category
from videosvoley.competitions.models import Match, League
from videosvoley.rosters.models import Person, PlayerRole, StaffRole

# Configurar logger
logger = logging.getLogger(__name__)


def user_is_approved(user):
    """Verifica si el usuario está aprobado para acceder al contenido"""
    return user.is_approved


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def team_list(request):
    """Vista para mostrar todos los equipos disponibles"""
    teams = Team.objects.filter(is_active=True).select_related('category', 'club').prefetch_related('player_roles__person', 'staff_roles__person')
    categories = Category.objects.filter(is_active=True).order_by('name')
    
    # Filtros
    category_filter = request.GET.get('category')
    club_filter = request.GET.get('club')
    search_query = request.GET.get('search', '').strip()
    show_all = request.GET.get('show_all', '0') == '1'
    
    # Aplicar filtro de categoría
    if category_filter:
        teams = teams.filter(category_id=category_filter)
    # Si no hay filtro de categoría, aplicar preferencias del usuario
    elif not show_all and request.user.preferred_categories.exists():
        user_categories = request.user.preferred_categories.all()
        teams = teams.filter(category__in=user_categories)
    
    # Aplicar filtro de club
    if club_filter:
        teams = teams.filter(club_id=club_filter)
    
    # Aplicar búsqueda
    if search_query:
        teams = teams.filter(
            Q(name__icontains=search_query) |
            Q(club__official_name__icontains=search_query) |
            Q(club__short_name__icontains=search_query)
        )
    
    # Ordenar por categoría y nombre
    teams = teams.order_by('category__name', 'name')
    
    # Paginación
    paginator = Paginator(teams, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Obtener clubs para filtro
    clubs = Club.objects.filter(is_active=True).order_by('official_name')
    
    return render(request, 'teams/team_list.html', {
        'page_obj': page_obj,
        'categories': categories,
        'clubs': clubs,
        'selected_category': category_filter,
        'selected_club': club_filter,
        'search_query': search_query,
        'show_all': show_all,
        'has_preferences': request.user.preferred_categories.exists(),
    })


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def team_detail(request, team_id):
    """Vista detallada de un equipo con su plantilla y partidos"""
    team = get_object_or_404(Team, id=team_id, is_active=True)
    
    # Obtener plantilla del equipo
    players = team.player_roles.select_related('person').order_by('position', 'person__last_name')
    staff = team.staff_roles.select_related('person').order_by('role', 'person__last_name')
    
    # Obtener partidos del equipo
    matches = Match.objects.filter(
        Q(home_team=team) | Q(away_team=team)
    ).select_related('home_team', 'away_team', 'league').order_by('-match_date')
    
    # Filtros de partidos
    status_filter = request.GET.get('status')
    if status_filter:
        matches = matches.filter(status=status_filter)
    
    # Paginación de partidos
    paginator = Paginator(matches, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Estadísticas del equipo
    total_matches = matches.count()
    won_matches = matches.filter(
        Q(home_team=team, home_score__gt=F('away_score')) |
        Q(away_team=team, away_score__gt=F('home_score'))
    ).count()
    
    return render(request, 'teams/team_detail.html', {
        'team': team,
        'players': players,
        'staff': staff,
        'page_obj': page_obj,
        'total_matches': total_matches,
        'won_matches': won_matches,
        'selected_status': status_filter,
    })


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def team_roster(request, team_id):
    """Vista de plantilla de un equipo específico"""
    team = get_object_or_404(Team, id=team_id, is_active=True)
    
    # Obtener plantilla completa
    players = team.player_roles.select_related('person').order_by('position', 'person__last_name')
    staff = team.staff_roles.select_related('person').order_by('role', 'person__last_name')
    
    # Agrupar jugadores por posición
    players_by_position = {}
    for player in players:
        position = player.position or 'Sin posición'
        if position not in players_by_position:
            players_by_position[position] = []
        players_by_position[position].append(player)
    
    # Agrupar staff por rol
    staff_by_role = {}
    for member in staff:
        role = member.role or 'Sin rol'
        if role not in staff_by_role:
            staff_by_role[role] = []
        staff_by_role[role].append(member)
    
    return render(request, 'teams/team_roster.html', {
        'team': team,
        'players_by_position': players_by_position,
        'staff_by_role': staff_by_role,
        'total_players': players.count(),
        'total_staff': staff.count(),
    })


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def club_detail(request, club_id):
    """Vista detallada de un club con todos sus equipos"""
    club = get_object_or_404(Club, id=club_id, is_active=True)
    
    # Obtener equipos del club
    teams = club.teams.filter(is_active=True).select_related('category').prefetch_related('player_roles__person', 'staff_roles__person')
    
    # Agrupar equipos por categoría
    teams_by_category = {}
    for team in teams:
        category = team.category.name if team.category else 'Sin categoría'
        if category not in teams_by_category:
            teams_by_category[category] = []
        teams_by_category[category].append(team)
    
    # Obtener partidos recientes del club
    recent_matches = Match.objects.filter(
        Q(home_team__club=club) | Q(away_team__club=club)
    ).select_related('home_team', 'away_team', 'league').order_by('-match_date')[:10]
    
    # Estadísticas del club
    total_teams = teams.count()
    total_players = sum(team.player_roles.count() for team in teams)
    total_staff = sum(team.staff_roles.count() for team in teams)
    
    return render(request, 'teams/club_detail.html', {
        'club': club,
        'teams_by_category': teams_by_category,
        'recent_matches': recent_matches,
        'total_teams': total_teams,
        'total_players': total_players,
        'total_staff': total_staff,
    })


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def club_list(request):
    """Vista para mostrar todos los clubs disponibles"""
    clubs = Club.objects.filter(is_active=True).prefetch_related('teams__category')
    
    # Filtros
    search_query = request.GET.get('search', '').strip()
    show_all = request.GET.get('show_all', '0') == '1'
    
    # Aplicar búsqueda
    if search_query:
        clubs = clubs.filter(
            Q(official_name__icontains=search_query) |
            Q(short_name__icontains=search_query) |
            Q(city__icontains=search_query) |
            Q(province__icontains=search_query)
        )
    
    # Ordenar por nombre oficial
    clubs = clubs.order_by('official_name')
    
    # Paginación
    paginator = Paginator(clubs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'teams/club_list.html', {
        'page_obj': page_obj,
        'search_query': search_query,
        'show_all': show_all,
    })


@login_required
def ajax_search_teams(request):
    """Vista AJAX para buscar equipos con autocompletado inteligente"""
    query = request.GET.get('q', '').strip()
    category_id = request.GET.get('category_id', '').strip()
    
    if len(query) < 2:
        return JsonResponse({'teams': []})
    
    # Buscar equipos existentes
    teams_query = Team.objects.filter(name__icontains=query, is_active=True)
    
    # Filtrar por categoría si se especifica
    if category_id:
        try:
            category = Category.objects.get(id=category_id)
            teams_query = teams_query.filter(category=category)
        except Category.DoesNotExist:
            pass
    
    # Limitar a 10 resultados
    teams = teams_query.select_related('category', 'club').order_by('name')[:10]
    
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
            'club': team.club.official_name if team.club else None,
        })
    
    return JsonResponse({'teams': teams_data})


@login_required
def ajax_teams_by_league_category(request):
    """Vista AJAX para obtener equipos filtrados por categoría de liga"""
    league_id = request.GET.get('league_id')
    filter_by_category = request.GET.get('filter_by_category', 'true').lower() == 'true'
    
    if league_id and filter_by_category:
        try:
            league = League.objects.get(id=league_id)
            
            if league.category:
                # Filtrar equipos por la categoría de la liga
                teams = Team.objects.filter(category=league.category, is_active=True).order_by('name')
            else:
                # Si la liga no tiene categoría, mostrar todos
                teams = Team.objects.filter(is_active=True).order_by('name')
        except League.DoesNotExist:
            teams = Team.objects.filter(is_active=True).order_by('name')
    else:
        # Sin filtrado o sin liga, mostrar todos los equipos
        teams = Team.objects.filter(is_active=True).order_by('name')
    
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
                club = Club.objects.get(id=club_id, is_active=True)
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


@login_required
def ajax_search_clubs(request):
    """Vista AJAX para buscar clubs con autocompletado"""
    query = request.GET.get('q', '').strip()
    
    if len(query) < 2:
        return JsonResponse({'clubs': []})
    
    # Buscar clubs existentes
    clubs_query = Club.objects.filter(
        Q(official_name__icontains=query) |
        Q(short_name__icontains=query) |
        Q(city__icontains=query)
    ).filter(is_active=True)
    
    # Limitar a 10 resultados
    clubs = clubs_query.order_by('official_name')[:10]
    
    # Formatear respuesta
    clubs_data = []
    for club in clubs:
        display_name = club.official_name
        if club.short_name and club.short_name != club.official_name:
            display_name += f" ({club.short_name})"
        if club.city:
            display_name += f" - {club.city}"
        
        clubs_data.append({
            'id': club.id,
            'name': club.official_name,
            'display': display_name,
            'short_name': club.short_name,
            'city': club.city,
        })
    
    return JsonResponse({'clubs': clubs_data})


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def roster_overview(request):
    """Vista general de todas las plantillas del club"""
    # Configuración del club
    CLUB_TEAM_NAME = 'SANT JOSEP'
    
    # Obtener equipos del club
    teams = Team.objects.filter(
        Q(name__icontains=CLUB_TEAM_NAME) | Q(club__official_name__icontains=CLUB_TEAM_NAME)
    ).filter(is_active=True).select_related('category', 'club').prefetch_related('player_roles__person', 'staff_roles__person')
    
    # Agrupar por categoría
    teams_by_category = {}
    for team in teams:
        category = team.category.name if team.category else 'Sin categoría'
        if category not in teams_by_category:
            teams_by_category[category] = []
        teams_by_category[category].append(team)
    
    # Estadísticas generales
    total_teams = teams.count()
    total_players = sum(team.player_roles.count() for team in teams)
    total_staff = sum(team.staff_roles.count() for team in teams)
    
    return render(request, 'teams/roster_overview.html', {
        'teams_by_category': teams_by_category,
        'total_teams': total_teams,
        'total_players': total_players,
        'total_staff': total_staff,
        'club_team_name': CLUB_TEAM_NAME,
    })