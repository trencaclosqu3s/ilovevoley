import requests
import logging
from typing import Dict, List, Optional
from django.utils import timezone
from .models import Club, Team

logger = logging.getLogger(__name__)


def fetch_club_logo_from_federation(club: Club) -> Optional[str]:
    """
    Obtiene el logo de un club desde la federación
    
    Args:
        club: Club object
    
    Returns:
        URL del logo o None si no se encuentra
    """
    if not club.federation_id:
        return None
    
    try:
        logo_url = club.logo_federation_url
        if logo_url:
            # Verificar que la URL es accesible
            response = requests.head(logo_url, timeout=10)
            if response.status_code == 200:
                return logo_url
    except Exception as e:
        logger.warning(f'Error fetching logo for club {club.official_name}: {e}')
    
    return None


def update_club_logos():
    """
    Actualiza los logos de todos los clubs desde la federación
    """
    clubs = Club.objects.filter(logo_url__isnull=True)
    updated_count = 0
    
    for club in clubs:
        logo_url = fetch_club_logo_from_federation(club)
        if logo_url:
            club.logo_url = logo_url
            club.save()
            updated_count += 1
            logger.info(f'Logo actualizado para {club.official_name}')
    
    logger.info(f'Logos actualizados: {updated_count} clubs')
    return updated_count


def match_teams_with_clubs():
    """
    Intenta hacer match automático entre equipos y clubs basado en nombres
    """
    teams_without_club = Team.objects.filter(club__isnull=True)
    matched_count = 0
    
    for team in teams_without_club:
        # Buscar club por similitud en el nombre
        potential_clubs = find_potential_clubs_for_team(team)
        
        if potential_clubs:
            # Usar el primer match (se puede mejorar la lógica)
            team.club = potential_clubs[0]
            team.save()
            matched_count += 1
            logger.info(f'Equipo {team.name} emparejado con club {team.club.official_name}')
    
    logger.info(f'Equipos emparejados: {matched_count}')
    return matched_count


def find_potential_clubs_for_team(team: Team) -> List[Club]:
    """
    Encuentra clubs potenciales para un equipo basado en similitud de nombres
    
    Args:
        team: Team object
    
    Returns:
        Lista de clubs potenciales
    """
    team_name = team.name.lower()
    potential_clubs = []
    
    # Buscar clubs que contengan palabras del nombre del equipo
    team_words = team_name.split()
    
    for club in Club.objects.all():
        club_name = club.official_name.lower()
        
        # Calcular similitud simple
        common_words = sum(1 for word in team_words if word in club_name)
        similarity = common_words / len(team_words) if team_words else 0
        
        if similarity > 0.3:  # Umbral de similitud
            potential_clubs.append((club, similarity))
    
    # Ordenar por similitud
    potential_clubs.sort(key=lambda x: x[1], reverse=True)
    return [club for club, _ in potential_clubs[:3]]  # Top 3


def get_team_statistics(team: Team) -> Dict:
    """
    Obtiene estadísticas detalladas de un equipo
    
    Args:
        team: Team object
    
    Returns:
        Diccionario con estadísticas
    """
    try:
        from videosvoley.competitions.models import Match, Standing
        
        # Estadísticas básicas
        stats = {
            'team_name': team.name,
            'club_name': team.club.official_name if team.club else 'Sin club',
            'category': team.category.name if team.category else 'Sin categoría',
            'is_active': team.is_active,
            'created_at': team.created_at.isoformat(),
        }
        
        # Estadísticas de partidos
        matches = team.get_matches()
        finished_matches = matches.filter(status='finished')
        
        stats['matches'] = {
            'total': matches.count(),
            'finished': finished_matches.count(),
            'scheduled': matches.filter(status='scheduled').count(),
            'in_progress': matches.filter(status='in_progress').count(),
            'postponed': matches.filter(status='postponed').count(),
            'cancelled': matches.filter(status='cancelled').count(),
        }
        
        # Estadísticas de victorias/derrotas
        wins = 0
        losses = 0
        
        for match in finished_matches:
            if match.home_score is not None and match.away_score is not None:
                if match.home_team == team:
                    if match.home_score > match.away_score:
                        wins += 1
                    else:
                        losses += 1
                else:  # away_team
                    if match.away_score > match.home_score:
                        wins += 1
                    else:
                        losses += 1
        
        stats['performance'] = {
            'wins': wins,
            'losses': losses,
            'win_percentage': round((wins / (wins + losses)) * 100, 1) if (wins + losses) > 0 else 0,
        }
        
        # Estadísticas de clasificación
        standings = team.get_standings()
        if standings.exists():
            latest_standing = standings.first()
            stats['current_standing'] = {
                'position': latest_standing.position,
                'league': latest_standing.league.name,
                'points': latest_standing.total_points,
                'played': latest_standing.played,
            }
        
        return stats
        
    except Exception as e:
        logger.error(f'Error getting team statistics: {e}')
        return {'error': str(e)}


def get_club_statistics(club: Club) -> Dict:
    """
    Obtiene estadísticas detalladas de un club
    
    Args:
        club: Club object
    
    Returns:
        Diccionario con estadísticas
    """
    try:
        teams = club.teams.all()
        active_teams = teams.filter(is_active=True)
        
        stats = {
            'club_name': club.official_name,
            'federation_id': club.federation_id,
            'province': club.province,
            'teams': {
                'total': teams.count(),
                'active': active_teams.count(),
                'inactive': teams.filter(is_active=False).count(),
            },
            'created_at': club.created_at.isoformat(),
        }
        
        # Estadísticas por categoría
        categories = {}
        for team in active_teams:
            if team.category:
                cat_name = team.category.name
                if cat_name not in categories:
                    categories[cat_name] = 0
                categories[cat_name] += 1
        
        stats['teams_by_category'] = categories
        
        # Estadísticas de partidos de todos los equipos
        total_matches = 0
        finished_matches = 0
        
        for team in active_teams:
            team_matches = team.get_matches()
            total_matches += team_matches.count()
            finished_matches += team_matches.filter(status='finished').count()
        
        stats['matches'] = {
            'total': total_matches,
            'finished': finished_matches,
        }
        
        return stats
        
    except Exception as e:
        logger.error(f'Error getting club statistics: {e}')
        return {'error': str(e)}


def export_teams_data(format='json') -> str:
    """
    Exporta datos de equipos en el formato especificado
    
    Args:
        format: Formato de exportación ('json', 'csv')
    
    Returns:
        Datos exportados como string
    """
    try:
        teams = Team.objects.select_related('club', 'category').all()
        
        if format == 'json':
            import json
            data = []
            for team in teams:
                data.append({
                    'id': team.id,
                    'name': team.name,
                    'federation_id': team.federation_id,
                    'club': team.club.official_name if team.club else None,
                    'category': team.category.name if team.category else None,
                    'is_active': team.is_active,
                    'created_at': team.created_at.isoformat(),
                })
            return json.dumps(data, indent=2, ensure_ascii=False)
        
        elif format == 'csv':
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Headers
            writer.writerow(['ID', 'Nombre', 'ID Federación', 'Club', 'Categoría', 'Activo', 'Creado'])
            
            # Data
            for team in teams:
                writer.writerow([
                    team.id,
                    team.name,
                    team.federation_id,
                    team.club.official_name if team.club else '',
                    team.category.name if team.category else '',
                    'Sí' if team.is_active else 'No',
                    team.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                ])
            
            return output.getvalue()
        
        else:
            raise ValueError(f'Formato no soportado: {format}')
            
    except Exception as e:
        logger.error(f'Error exporting teams data: {e}')
        return f'Error: {str(e)}'


def import_teams_from_federation_data(federation_data: List[Dict]) -> int:
    """
    Importa equipos desde datos de la federación
    
    Args:
        federation_data: Lista de diccionarios con datos de equipos
    
    Returns:
        Número de equipos importados
    """
    imported_count = 0
    
    try:
        for team_data in federation_data:
            # Crear o actualizar equipo
            team, created = Team.objects.get_or_create(
                federation_id=team_data.get('federation_id'),
                defaults={
                    'name': team_data.get('name', ''),
                    'is_active': team_data.get('is_active', True),
                }
            )
            
            if created:
                imported_count += 1
                logger.info(f'Equipo importado: {team.name}')
            
            # Actualizar datos si el equipo ya existía
            if not created and team_data.get('name') != team.name:
                team.name = team_data.get('name', team.name)
                team.is_active = team_data.get('is_active', team.is_active)
                team.save()
                logger.info(f'Equipo actualizado: {team.name}')
    
    except Exception as e:
        logger.error(f'Error importing teams: {e}')
    
    return imported_count