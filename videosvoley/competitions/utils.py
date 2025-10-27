"""
Utilidades para la gestión de competiciones.
"""
from django.db.models import F, Q
from .models import Match, Standing


def update_league_standings(league):
    """
    Actualiza las clasificaciones de una liga basándose en los partidos finalizados
    
    Args:
        league: Instancia de League
    """
    if not league:
        return
    
    # Obtener todos los equipos que han jugado en la liga
    teams_in_league = set()
    
    # Equipos con ForeignKey
    home_teams = Match.objects.filter(
        league=league,
        status='finished',
        home_team__isnull=False
    ).values_list('home_team', flat=True).distinct()
    
    away_teams = Match.objects.filter(
        league=league,
        status='finished',
        away_team__isnull=False
    ).values_list('away_team', flat=True).distinct()
    
    teams_in_league.update(home_teams)
    teams_in_league.update(away_teams)
    
    # Procesar cada equipo
    for team_id in teams_in_league:
        try:
            from videosvoley.teams.models import Team
            team = Team.objects.get(id=team_id)
            
            # Calcular estadísticas del equipo
            stats = calculate_team_stats(team, league)
            
            # Crear o actualizar clasificación
            standing, created = Standing.objects.get_or_create(
                league=league,
                team=team,
                defaults=stats
            )
            
            if not created:
                # Actualizar estadísticas existentes
                for key, value in stats.items():
                    setattr(standing, key, value)
                standing.save()
                
        except Exception as e:
            print(f"Error actualizando clasificación para equipo {team_id}: {e}")


def calculate_team_stats(team, league):
    """
    Calcula las estadísticas de un equipo en una liga
    
    Args:
        team: Instancia de Team
        league: Instancia de League
        
    Returns:
        dict: Estadísticas del equipo
    """
    # Partidos como local
    home_matches = Match.objects.filter(
        league=league,
        home_team=team,
        status='finished',
        home_score__isnull=False,
        away_score__isnull=False
    )
    
    # Partidos como visitante
    away_matches = Match.objects.filter(
        league=league,
        away_team=team,
        status='finished',
        home_score__isnull=False,
        away_score__isnull=False
    )
    
    # Calcular estadísticas
    matches_played = home_matches.count() + away_matches.count()
    matches_won = 0
    matches_drawn = 0
    matches_lost = 0
    points_for = 0
    points_against = 0
    
    # Procesar partidos como local
    for match in home_matches:
        points_for += match.home_score
        points_against += match.away_score
        
        if match.home_score > match.away_score:
            matches_won += 1
        elif match.home_score == match.away_score:
            matches_drawn += 1
        else:
            matches_lost += 1
    
    # Procesar partidos como visitante
    for match in away_matches:
        points_for += match.away_score
        points_against += match.home_score
        
        if match.away_score > match.home_score:
            matches_won += 1
        elif match.away_score == match.home_score:
            matches_drawn += 1
        else:
            matches_lost += 1
    
    # Calcular puntos (3 por victoria, 1 por empate)
    points = matches_won * 3 + matches_drawn
    
    return {
        'matches_played': matches_played,
        'matches_won': matches_won,
        'matches_drawn': matches_drawn,
        'matches_lost': matches_lost,
        'points_for': points_for,
        'points_against': points_against,
        'points': points,
    }


def get_league_standings(league):
    """
    Obtiene las clasificaciones de una liga ordenadas por posición
    
    Args:
        league: Instancia de League
        
    Returns:
        QuerySet: Clasificaciones ordenadas
    """
    return Standing.objects.filter(league=league).order_by('position')


def get_team_matches(team, league=None, status=None):
    """
    Obtiene los partidos de un equipo
    
    Args:
        team: Instancia de Team
        league: Instancia de League (opcional)
        status: Estado del partido (opcional)
        
    Returns:
        QuerySet: Partidos del equipo
    """
    matches = Match.objects.filter(
        Q(home_team=team) | Q(away_team=team)
    ).select_related('home_team', 'away_team', 'league')
    
    if league:
        matches = matches.filter(league=league)
    
    if status:
        matches = matches.filter(status=status)
    
    return matches.order_by('-match_date')


def get_upcoming_matches(league=None, limit=10):
    """
    Obtiene los próximos partidos
    
    Args:
        league: Instancia de League (opcional)
        limit: Número máximo de partidos
        
    Returns:
        QuerySet: Próximos partidos
    """
    from django.utils import timezone
    
    matches = Match.objects.filter(
        match_date__gte=timezone.now(),
        status__in=['scheduled', 'in_progress']
    ).select_related('home_team', 'away_team', 'league')
    
    if league:
        matches = matches.filter(league=league)
    
    return matches.order_by('match_date')[:limit]


def get_recent_matches(league=None, limit=10):
    """
    Obtiene los partidos recientes
    
    Args:
        league: Instancia de League (opcional)
        limit: Número máximo de partidos
        
    Returns:
        QuerySet: Partidos recientes
    """
    from django.utils import timezone
    
    matches = Match.objects.filter(
        match_date__lt=timezone.now(),
        status='finished'
    ).select_related('home_team', 'away_team', 'league')
    
    if league:
        matches = matches.filter(league=league)
    
    return matches.order_by('-match_date')[:limit]


def get_league_stats(league):
    """
    Obtiene estadísticas generales de una liga
    
    Args:
        league: Instancia de League
        
    Returns:
        dict: Estadísticas de la liga
    """
    matches = Match.objects.filter(league=league)
    
    total_matches = matches.count()
    finished_matches = matches.filter(status='finished').count()
    scheduled_matches = matches.filter(status='scheduled').count()
    
    # Calcular goles totales
    total_goals = 0
    for match in matches.filter(status='finished', home_score__isnull=False, away_score__isnull=False):
        total_goals += match.home_score + match.away_score
    
    return {
        'total_matches': total_matches,
        'finished_matches': finished_matches,
        'scheduled_matches': scheduled_matches,
        'total_goals': total_goals,
        'average_goals_per_match': total_goals / finished_matches if finished_matches > 0 else 0,
    }