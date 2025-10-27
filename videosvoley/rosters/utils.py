"""
Utilidades para la gestión de plantillas y personas.
"""
from django.db.models import Q, Count, F
from .models import Person, PlayerRole, StaffRole


def get_person_stats(person):
    """
    Obtiene estadísticas de una persona
    
    Args:
        person: Instancia de Person
        
    Returns:
        dict: Estadísticas de la persona
    """
    # Roles de la persona
    player_roles = person.player_roles.filter(is_active=True)
    staff_roles = person.staff_roles.filter(is_active=True)
    
    # Equipos únicos
    player_teams = set(player_roles.values_list('team__name', flat=True))
    staff_teams = set(staff_roles.values_list('team__name', flat=True))
    all_teams = player_teams.union(staff_teams)
    
    # Categorías únicas
    player_categories = set(player_roles.values_list('team__category__name', flat=True))
    staff_categories = set(staff_roles.values_list('team__category__name', flat=True))
    all_categories = player_categories.union(staff_categories)
    
    return {
        'total_teams': len(all_teams),
        'total_categories': len(all_categories),
        'player_roles': player_roles.count(),
        'staff_roles': staff_roles.count(),
        'active_roles': player_roles.count() + staff_roles.count(),
        'teams': list(all_teams),
        'categories': list(all_categories),
    }


def get_team_roster_stats(team):
    """
    Obtiene estadísticas de plantilla de un equipo
    
    Args:
        team: Instancia de Team
        
    Returns:
        dict: Estadísticas de la plantilla
    """
    # Jugadores
    players = team.player_roles.filter(is_active=True)
    active_players = players.count()
    
    # Staff
    staff = team.staff_roles.filter(is_active=True)
    active_staff = staff.count()
    
    # Posiciones de jugadores
    positions = players.values_list('position', flat=True).distinct()
    positions_count = {}
    for position in positions:
        if position:
            positions_count[position] = players.filter(position=position).count()
    
    # Roles de staff
    roles = staff.values_list('role', flat=True).distinct()
    roles_count = {}
    for role in roles:
        if role:
            roles_count[role] = staff.filter(role=role).count()
    
    return {
        'total_players': active_players,
        'total_staff': active_staff,
        'total_members': active_players + active_staff,
        'positions_count': positions_count,
        'roles_count': roles_count,
        'unique_positions': len(positions_count),
        'unique_roles': len(roles_count),
    }


def get_persons_by_team(team, role_type=None):
    """
    Obtiene personas de un equipo específico
    
    Args:
        team: Instancia de Team
        role_type: 'player', 'staff', o None para ambos
        
    Returns:
        QuerySet: Personas del equipo
    """
    if role_type == 'player':
        return Person.objects.filter(player_roles__team=team, player_roles__is_active=True).distinct()
    elif role_type == 'staff':
        return Person.objects.filter(staff_roles__team=team, staff_roles__is_active=True).distinct()
    else:  # both
        return Person.objects.filter(
            Q(player_roles__team=team, player_roles__is_active=True) |
            Q(staff_roles__team=team, staff_roles__is_active=True)
        ).distinct()


def get_persons_by_category(category, role_type=None):
    """
    Obtiene personas de una categoría específica
    
    Args:
        category: Instancia de Category
        role_type: 'player', 'staff', o None para ambos
        
    Returns:
        QuerySet: Personas de la categoría
    """
    if role_type == 'player':
        return Person.objects.filter(
            player_roles__team__category=category,
            player_roles__is_active=True
        ).distinct()
    elif role_type == 'staff':
        return Person.objects.filter(
            staff_roles__team__category=category,
            staff_roles__is_active=True
        ).distinct()
    else:  # both
        return Person.objects.filter(
            Q(player_roles__team__category=category, player_roles__is_active=True) |
            Q(staff_roles__team__category=category, staff_roles__is_active=True)
        ).distinct()


def search_persons(query, team=None, role_type=None):
    """
    Busca personas con filtros opcionales
    
    Args:
        query: Término de búsqueda
        team: Filtro por equipo (opcional)
        role_type: Filtro por tipo de rol (opcional)
        
    Returns:
        QuerySet: Personas que coinciden con la búsqueda
    """
    persons = Person.objects.filter(
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query) |
        Q(email__icontains=query) |
        Q(phone__icontains=query)
    )
    
    if team:
        persons = persons.filter(
            Q(player_roles__team=team) | Q(staff_roles__team=team)
        ).distinct()
    
    if role_type == 'player':
        persons = persons.filter(player_roles__isnull=False).distinct()
    elif role_type == 'staff':
        persons = persons.filter(staff_roles__isnull=False).distinct()
    
    return persons.order_by('last_name', 'first_name')


def get_person_teams(person):
    """
    Obtiene todos los equipos de una persona
    
    Args:
        person: Instancia de Person
        
    Returns:
        dict: Equipos agrupados por tipo de rol
    """
    player_teams = person.player_roles.filter(is_active=True).select_related('team', 'team__category')
    staff_teams = person.staff_roles.filter(is_active=True).select_related('team', 'team__category')
    
    return {
        'player_teams': player_teams,
        'staff_teams': staff_teams,
        'all_teams': list(player_teams) + list(staff_teams),
    }


def get_team_roster_by_position(team):
    """
    Obtiene la plantilla de un equipo organizada por posición
    
    Args:
        team: Instancia de Team
        
    Returns:
        dict: Plantilla organizada por posición
    """
    # Jugadores por posición
    players_by_position = {}
    for player in team.player_roles.filter(is_active=True).select_related('person').order_by('position', 'person__last_name'):
        position = player.position or 'Sin posición'
        if position not in players_by_position:
            players_by_position[position] = []
        players_by_position[position].append(player)
    
    # Staff por rol
    staff_by_role = {}
    for member in team.staff_roles.filter(is_active=True).select_related('person').order_by('role', 'person__last_name'):
        role = member.role or 'Sin rol'
        if role not in staff_by_role:
            staff_by_role[role] = []
        staff_by_role[role].append(member)
    
    return {
        'players_by_position': players_by_position,
        'staff_by_role': staff_by_role,
        'total_players': sum(len(players) for players in players_by_position.values()),
        'total_staff': sum(len(staff) for staff in staff_by_role.values()),
    }


def get_club_roster_stats(club):
    """
    Obtiene estadísticas de plantilla de un club
    
    Args:
        club: Instancia de Club
        
    Returns:
        dict: Estadísticas de la plantilla del club
    """
    # Obtener equipos del club
    teams = club.teams.filter(is_active=True)
    
    # Estadísticas por equipo
    team_stats = []
    total_players = 0
    total_staff = 0
    
    for team in teams:
        stats = get_team_roster_stats(team)
        team_stats.append({
            'team': team,
            'stats': stats
        })
        total_players += stats['total_players']
        total_staff += stats['total_staff']
    
    # Personas únicas del club
    unique_persons = Person.objects.filter(
        Q(player_roles__team__club=club, player_roles__is_active=True) |
        Q(staff_roles__team__club=club, staff_roles__is_active=True)
    ).distinct().count()
    
    return {
        'total_teams': teams.count(),
        'total_players': total_players,
        'total_staff': total_staff,
        'total_members': total_players + total_staff,
        'unique_persons': unique_persons,
        'team_stats': team_stats,
    }


def get_person_roles_summary(person):
    """
    Obtiene un resumen de todos los roles de una persona
    
    Args:
        person: Instancia de Person
        
    Returns:
        dict: Resumen de roles
    """
    player_roles = person.player_roles.filter(is_active=True).select_related('team', 'team__category')
    staff_roles = person.staff_roles.filter(is_active=True).select_related('team', 'team__category')
    
    # Agrupar por categoría
    roles_by_category = {}
    
    for role in player_roles:
        category = role.team.category.name if role.team.category else 'Sin categoría'
        if category not in roles_by_category:
            roles_by_category[category] = {'player': [], 'staff': []}
        roles_by_category[category]['player'].append(role)
    
    for role in staff_roles:
        category = role.team.category.name if role.team.category else 'Sin categoría'
        if category not in roles_by_category:
            roles_by_category[category] = {'player': [], 'staff': []}
        roles_by_category[category]['staff'].append(role)
    
    return {
        'roles_by_category': roles_by_category,
        'total_player_roles': player_roles.count(),
        'total_staff_roles': staff_roles.count(),
        'total_roles': player_roles.count() + staff_roles.count(),
        'categories': list(roles_by_category.keys()),
    }


def get_roster_statistics():
    """
    Obtiene estadísticas generales de todas las plantillas
    
    Returns:
        dict: Estadísticas generales
    """
    # Personas totales
    total_persons = Person.objects.count()
    
    # Roles activos
    active_player_roles = PlayerRole.objects.filter(is_active=True).count()
    active_staff_roles = StaffRole.objects.filter(is_active=True).count()
    
    # Equipos con plantilla
    teams_with_roster = Team.objects.filter(
        Q(player_roles__isnull=False) | Q(staff_roles__isnull=False)
    ).distinct().count()
    
    # Personas con múltiples roles
    persons_with_multiple_roles = Person.objects.annotate(
        role_count=Count('player_roles', filter=Q(player_roles__is_active=True)) +
                   Count('staff_roles', filter=Q(staff_roles__is_active=True))
    ).filter(role_count__gt=1).count()
    
    return {
        'total_persons': total_persons,
        'active_player_roles': active_player_roles,
        'active_staff_roles': active_staff_roles,
        'total_active_roles': active_player_roles + active_staff_roles,
        'teams_with_roster': teams_with_roster,
        'persons_with_multiple_roles': persons_with_multiple_roles,
    }