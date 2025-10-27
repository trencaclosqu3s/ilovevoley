"""
Utilidades para la gestión de equipos y clubs.
"""
from django.db.models import Q, Count, F
from .models import Team, Club


def get_team_stats(team):
    """
    Obtiene estadísticas de un equipo
    
    Args:
        team: Instancia de Team
        
    Returns:
        dict: Estadísticas del equipo
    """
    from videosvoley.competitions.models import Match
    
    # Partidos del equipo
    matches = Match.objects.filter(
        Q(home_team=team) | Q(away_team=team)
    )
    
    total_matches = matches.count()
    won_matches = matches.filter(
        Q(home_team=team, home_score__gt=F('away_score')) |
        Q(away_team=team, away_score__gt=F('home_score'))
    ).count()
    
    drawn_matches = matches.filter(
        Q(home_team=team, home_score=F('away_score')) |
        Q(away_team=team, away_score=F('home_score'))
    ).count()
    
    lost_matches = total_matches - won_matches - drawn_matches
    
    # Plantilla
    total_players = team.player_roles.count()
    total_staff = team.staff_roles.count()
    
    return {
        'total_matches': total_matches,
        'won_matches': won_matches,
        'drawn_matches': drawn_matches,
        'lost_matches': lost_matches,
        'win_percentage': (won_matches / total_matches * 100) if total_matches > 0 else 0,
        'total_players': total_players,
        'total_staff': total_staff,
    }


def get_club_stats(club):
    """
    Obtiene estadísticas de un club
    
    Args:
        club: Instancia de Club
        
    Returns:
        dict: Estadísticas del club
    """
    # Equipos del club
    teams = club.teams.filter(is_active=True)
    total_teams = teams.count()
    
    # Plantilla total
    total_players = 0
    total_staff = 0
    for team in teams:
        total_players += team.player_roles.count()
        total_staff += team.staff_roles.count()
    
    # Partidos del club
    from videosvoley.competitions.models import Match
    matches = Match.objects.filter(
        Q(home_team__club=club) | Q(away_team__club=club)
    )
    
    total_matches = matches.count()
    won_matches = matches.filter(
        Q(home_team__club=club, home_score__gt=F('away_score')) |
        Q(away_team__club=club, away_score__gt=F('home_score'))
    ).count()
    
    return {
        'total_teams': total_teams,
        'total_players': total_players,
        'total_staff': total_staff,
        'total_matches': total_matches,
        'won_matches': won_matches,
        'win_percentage': (won_matches / total_matches * 100) if total_matches > 0 else 0,
    }


def get_teams_by_category(category):
    """
    Obtiene equipos de una categoría específica
    
    Args:
        category: Instancia de Category
        
    Returns:
        QuerySet: Equipos de la categoría
    """
    return Team.objects.filter(category=category, is_active=True).select_related('club')


def get_teams_by_club(club):
    """
    Obtiene equipos de un club específico
    
    Args:
        club: Instancia de Club
        
    Returns:
        QuerySet: Equipos del club
    """
    return club.teams.filter(is_active=True).select_related('category')


def get_clubs_by_province(province):
    """
    Obtiene clubs de una provincia específica
    
    Args:
        province: Nombre de la provincia
        
    Returns:
        QuerySet: Clubs de la provincia
    """
    return Club.objects.filter(province__icontains=province, is_active=True)


def search_teams(query, category=None, club=None):
    """
    Busca equipos con filtros opcionales
    
    Args:
        query: Término de búsqueda
        category: Filtro por categoría (opcional)
        club: Filtro por club (opcional)
        
    Returns:
        QuerySet: Equipos que coinciden con la búsqueda
    """
    teams = Team.objects.filter(
        Q(name__icontains=query) |
        Q(club__official_name__icontains=query) |
        Q(club__short_name__icontains=query)
    ).filter(is_active=True)
    
    if category:
        teams = teams.filter(category=category)
    
    if club:
        teams = teams.filter(club=club)
    
    return teams.select_related('category', 'club').order_by('name')


def search_clubs(query):
    """
    Busca clubs por término de búsqueda
    
    Args:
        query: Término de búsqueda
        
    Returns:
        QuerySet: Clubs que coinciden con la búsqueda
    """
    return Club.objects.filter(
        Q(official_name__icontains=query) |
        Q(short_name__icontains=query) |
        Q(city__icontains=query) |
        Q(province__icontains=query)
    ).filter(is_active=True).order_by('official_name')


def get_team_roster(team):
    """
    Obtiene la plantilla completa de un equipo
    
    Args:
        team: Instancia de Team
        
    Returns:
        dict: Plantilla del equipo organizada por posición/rol
    """
    # Jugadores por posición
    players_by_position = {}
    for player in team.player_roles.select_related('person').order_by('position', 'person__last_name'):
        position = player.position or 'Sin posición'
        if position not in players_by_position:
            players_by_position[position] = []
        players_by_position[position].append(player)
    
    # Staff por rol
    staff_by_role = {}
    for member in team.staff_roles.select_related('person').order_by('role', 'person__last_name'):
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


def get_club_teams_by_category(club):
    """
    Obtiene equipos de un club agrupados por categoría
    
    Args:
        club: Instancia de Club
        
    Returns:
        dict: Equipos agrupados por categoría
    """
    teams = club.teams.filter(is_active=True).select_related('category')
    
    teams_by_category = {}
    for team in teams:
        category = team.category.name if team.category else 'Sin categoría'
        if category not in teams_by_category:
            teams_by_category[category] = []
        teams_by_category[category].append(team)
    
    return teams_by_category


def get_team_matches(team, limit=10):
    """
    Obtiene partidos recientes de un equipo
    
    Args:
        team: Instancia de Team
        limit: Número máximo de partidos
        
    Returns:
        QuerySet: Partidos del equipo
    """
    from videosvoley.competitions.models import Match
    
    return Match.objects.filter(
        Q(home_team=team) | Q(away_team=team)
    ).select_related('home_team', 'away_team', 'league').order_by('-match_date')[:limit]


def get_club_matches(club, limit=10):
    """
    Obtiene partidos recientes de un club
    
    Args:
        club: Instancia de Club
        limit: Número máximo de partidos
        
    Returns:
        QuerySet: Partidos del club
    """
    from videosvoley.competitions.models import Match
    
    return Match.objects.filter(
        Q(home_team__club=club) | Q(away_team__club=club)
    ).select_related('home_team', 'away_team', 'league').order_by('-match_date')[:limit]


def get_team_standings(team):
    """
    Obtiene clasificaciones de un equipo
    
    Args:
        team: Instancia de Team
        
    Returns:
        QuerySet: Clasificaciones del equipo
    """
    from videosvoley.competitions.models import Standing
    
    return Standing.objects.filter(team=team).select_related('league').order_by('league__name')


def get_club_standings(club):
    """
    Obtiene clasificaciones de todos los equipos de un club
    
    Args:
        club: Instancia de Club
        
    Returns:
        QuerySet: Clasificaciones de los equipos del club
    """
    from videosvoley.competitions.models import Standing
    
    return Standing.objects.filter(team__club=club).select_related('team', 'league').order_by('league__name', 'position')