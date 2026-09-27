import logging
import re

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from ilovevoley.core.mixins import get_club_team_name_filter
from ilovevoley.core.models import Category, Season
from ilovevoley.core.season_utils import resolve_season_filter
from ilovevoley.core.tenancy import get_tenant_object_or_404
from ilovevoley.core.tenant_utils import tenant_access_required
from ilovevoley.rosters.models import PlayerRole, StaffRole
from ilovevoley.teams.models import Club, Team

logger = logging.getLogger(__name__)

TEAM_NAME_REGEX = re.compile(r"^[\w \.\-'\(\)/&]{2,100}$", re.UNICODE)


@require_POST
@tenant_access_required(manager=True)
def ajax_register_team(request):
    """Vista AJAX para registrar un nuevo equipo desde el formulario de amistosos"""
    try:
        raw_name = request.POST.get('name', '')
        if not isinstance(raw_name, str):
            raw_name = ''
        team_name = raw_name.strip()
        category_id = request.POST.get('category_id', '').strip()

        if (
            not raw_name
            or not team_name
            or any(ord(c) < 32 or ord(c) == 127 for c in raw_name)
            or len(team_name) < 2
            or len(team_name) > 100
            or not TEAM_NAME_REGEX.match(team_name)
        ):
            return JsonResponse({'success': False, 'error': 'Nombre de equipo no válido'}, status=400)

        if not category_id:
            return JsonResponse({'success': False, 'error': 'La categoría es requerida'})

        # Validar categoría
        try:
            category = Category.objects.get(id=category_id, is_active=True)
        except Category.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Categoría no válida'})

        # Asignar club del tenant ignorando cualquier club_id del payload
        club = getattr(request.tenant, 'club', None)
        
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


@tenant_access_required()
def team_list(request):
    """Lista de equipos del club con información de plantillas"""
    # Obtener categorías del usuario para filtrar
    user_categories = request.user.preferred_categories.all() if request.user.preferred_categories.exists() else Category.objects.filter(is_active=True)

    # Query base para equipos del club
    teams_query = Team.objects.select_related("category", "club").prefetch_related(
        "player_roles", "staff_roles"
    ).filter(is_active=True).filter(get_club_team_name_filter(request.tenant))
    
    # Filtrar por categorías preferidas del usuario
    category_filter = request.GET.get("category")
    show_all = request.GET.get("show_all", "0") == "1"
    
    if not show_all and not category_filter:
        teams_query = teams_query.filter(category__in=user_categories)
    elif category_filter:
        teams_query = teams_query.filter(category_id=category_filter)
    
    # Ordenar por categoría y nombre
    teams = teams_query.order_by("category__name", "name")

    # Temporada a mostrar (activa por defecto)
    season_filter, selected_season = resolve_season_filter(request)

    # Añadir contadores de plantilla usando nueva estructura Person-Role
    for team in teams:
        players = team.player_roles.filter(is_active=True)
        staff = team.staff_roles.filter(is_active=True)
        if season_filter:
            players = players.filter(season=season_filter)
            staff = staff.filter(season=season_filter)
        team.active_players_count = players.count()
        team.active_staff_count = staff.count()
    
    # Obtener categorías para el filtro
    categories = Category.objects.filter(is_active=True).order_by("name")
    
    context = {
        "teams": teams,
        "categories": categories,
        "seasons": Season.objects.all(),
        "selected_season": selected_season,
        "selected_category": category_filter,
        "show_all": show_all,
        "user_categories": user_categories,
    }
    
    return render(request, "teams/team_list.html", context)


@tenant_access_required()
def team_roster(request, team_id):
    """Vista de plantilla de un equipo específico"""
    team = get_tenant_object_or_404(
        Team.objects.select_related("category", "club"),
        request.tenant, user=request.user, id=team_id,
    )
    
    # Temporada a mostrar (activa por defecto)
    season_filter, selected_season = resolve_season_filter(request)

    # Obtener jugadores activos ordenados por número de dorsal usando nueva estructura
    player_roles = team.player_roles.filter(is_active=True)
    staff_roles = team.staff_roles.filter(is_active=True)
    if season_filter:
        player_roles = player_roles.filter(season=season_filter)
        staff_roles = staff_roles.filter(season=season_filter)
    player_roles = player_roles.select_related('person').order_by("jersey_number", "person__last_name", "person__first_name")
    staff_roles = staff_roles.select_related('person').order_by("role", "person__last_name", "person__first_name")
    
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
    position_choices = PlayerRole.POSITION_CHOICES
    role_choices = StaffRole.STAFF_ROLES
    
    context = {
        "team": team,
        "player_roles": player_roles,
        "staff_roles": staff_roles,
        "stats": stats,
        "position_choices": position_choices,
        "role_choices": role_choices,
        "seasons": Season.objects.all(),
        "selected_season": selected_season,
        "season_filtered": "season" in request.GET,
        "selected_position": position_filter,
        "selected_role": role_filter,
    }
    
    return render(request, "teams/team_roster.html", context)


__all__ = [
    'ajax_register_team',
    'team_list',
    'team_roster',
]
