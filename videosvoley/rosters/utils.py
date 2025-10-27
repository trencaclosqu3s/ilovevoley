import logging
from typing import Dict, List, Optional, Tuple
from django.utils import timezone
from django.db.models import Q, Count, Avg
from .models import Person, PlayerRole, StaffRole

logger = logging.getLogger(__name__)


def get_roster_statistics(team) -> Dict:
    """
    Obtiene estadísticas detalladas de la plantilla de un equipo
    
    Args:
        team: Team object
    
    Returns:
        Diccionario con estadísticas de la plantilla
    """
    try:
        # Obtener roles activos
        players = PlayerRole.objects.filter(team=team, is_active=True)
        staff = StaffRole.objects.filter(team=team, is_active=True)
        
        # Estadísticas básicas
        stats = {
            'team_name': team.name,
            'team_category': team.category.name if team.category else 'Sin categoría',
            'total_players': players.count(),
            'total_staff': staff.count(),
            'total_people': players.count() + staff.count(),
        }
        
        # Estadísticas de jugadores
        players_with_jersey = players.filter(jersey_number__isnull=False)
        positions = players.values_list('position', flat=True).distinct()
        
        stats['players'] = {
            'with_jersey': players_with_jersey.count(),
            'without_jersey': players.filter(jersey_number__isnull=True).count(),
            'positions': list(positions),
            'position_distribution': {
                pos: players.filter(position=pos).count() 
                for pos in positions
            },
            'jersey_numbers': list(players_with_jersey.values_list('jersey_number', flat=True)),
        }
        
        # Estadísticas de staff
        roles = staff.values_list('role', flat=True).distinct()
        
        stats['staff'] = {
            'roles': list(roles),
            'role_distribution': {
                role: staff.filter(role=role).count() 
                for role in roles
            },
            'coaches': staff.filter(role__in=['head_coach', 'assistant_coach']).count(),
            'delegates': staff.filter(role='delegate').count(),
        }
        
        # Estadísticas de edad
        players_with_age = players.filter(person__birth_date__isnull=False)
        if players_with_age.exists():
            ages = [role.person.age for role in players_with_age if role.person.age is not None]
            if ages:
                stats['age'] = {
                    'average': round(sum(ages) / len(ages), 1),
                    'min': min(ages),
                    'max': max(ages),
                    'distribution': get_age_distribution(ages),
                }
        
        return stats
        
    except Exception as e:
        logger.error(f'Error getting roster statistics: {e}')
        return {'error': str(e)}


def get_age_distribution(ages: List[int]) -> Dict[str, int]:
    """
    Obtiene la distribución de edades por rangos
    
    Args:
        ages: Lista de edades
    
    Returns:
        Diccionario con distribución por rangos
    """
    distribution = {
        '5-12': 0,   # Infantil
        '13-16': 0,  # Cadete
        '17-19': 0,  # Juvenil
        '20-35': 0,  # Senior
        '36+': 0,    # Veterano
    }
    
    for age in ages:
        if 5 <= age <= 12:
            distribution['5-12'] += 1
        elif 13 <= age <= 16:
            distribution['13-16'] += 1
        elif 17 <= age <= 19:
            distribution['17-19'] += 1
        elif 20 <= age <= 35:
            distribution['20-35'] += 1
        else:
            distribution['36+'] += 1
    
    return distribution


def get_person_statistics(person: Person) -> Dict:
    """
    Obtiene estadísticas detalladas de una persona
    
    Args:
        person: Person object
    
    Returns:
        Diccionario con estadísticas de la persona
    """
    try:
        # Obtener roles activos
        player_roles = person.get_player_roles()
        staff_roles = person.get_staff_roles()
        
        # Estadísticas básicas
        stats = {
            'person_name': person.full_name,
            'age': person.age,
            'is_active': person.is_active,
            'contact_info': person.contact_info,
        }
        
        # Estadísticas de roles de jugador
        stats['player_roles'] = {
            'total_teams': player_roles.values('team').distinct().count(),
            'positions': list(player_roles.values_list('position', flat=True).distinct()),
            'jersey_numbers': list(player_roles.filter(jersey_number__isnull=False).values_list('jersey_number', flat=True)),
            'teams': [
                {
                    'team_name': role.team.name,
                    'position': role.display_position,
                    'jersey_number': role.jersey_number,
                }
                for role in player_roles
            ],
        }
        
        # Estadísticas de roles de staff
        stats['staff_roles'] = {
            'total_teams': staff_roles.values('team').distinct().count(),
            'roles': list(staff_roles.values_list('role', flat=True).distinct()),
            'teams': [
                {
                    'team_name': role.team.name,
                    'role': role.display_role,
                }
                for role in staff_roles
            ],
        }
        
        # Estadísticas generales
        all_teams = person.get_all_active_teams()
        stats['general'] = {
            'total_teams': len(all_teams),
            'teams': [team.name for team in all_teams],
            'is_player': player_roles.exists(),
            'is_staff': staff_roles.exists(),
            'is_both': player_roles.exists() and staff_roles.exists(),
        }
        
        return stats
        
    except Exception as e:
        logger.error(f'Error getting person statistics: {e}')
        return {'error': str(e)}


def export_roster_data(team, format='json') -> str:
    """
    Exporta datos de la plantilla de un equipo
    
    Args:
        team: Team object
        format: Formato de exportación ('json', 'csv')
    
    Returns:
        Datos exportados como string
    """
    try:
        # Obtener datos de la plantilla
        players = PlayerRole.objects.filter(team=team, is_active=True).select_related('person')
        staff = StaffRole.objects.filter(team=team, is_active=True).select_related('person')
        
        if format == 'json':
            import json
            data = {
                'team': {
                    'name': team.name,
                    'category': team.category.name if team.category else 'Sin categoría',
                    'club': team.club.official_name if team.club else 'Sin club',
                },
                'players': [
                    {
                        'name': role.person.full_name,
                        'jersey_number': role.jersey_number,
                        'position': role.display_position,
                        'age': role.person.age,
                        'email': role.person.email,
                        'phone': role.person.phone,
                    }
                    for role in players
                ],
                'staff': [
                    {
                        'name': role.person.full_name,
                        'role': role.display_role,
                        'age': role.person.age,
                        'email': role.person.email,
                        'phone': role.person.phone,
                    }
                    for role in staff
                ],
                'exported_at': timezone.now().isoformat(),
            }
            return json.dumps(data, indent=2, ensure_ascii=False)
        
        elif format == 'csv':
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Headers
            writer.writerow(['Tipo', 'Nombre', 'Número', 'Posición/Rol', 'Edad', 'Email', 'Teléfono'])
            
            # Jugadores
            for role in players:
                writer.writerow([
                    'Jugador',
                    role.person.full_name,
                    role.jersey_number or '',
                    role.display_position,
                    role.person.age or '',
                    role.person.email or '',
                    role.person.phone or '',
                ])
            
            # Staff
            for role in staff:
                writer.writerow([
                    'Staff',
                    role.person.full_name,
                    '',
                    role.display_role,
                    role.person.age or '',
                    role.person.email or '',
                    role.person.phone or '',
                ])
            
            return output.getvalue()
        
        else:
            raise ValueError(f'Formato no soportado: {format}')
            
    except Exception as e:
        logger.error(f'Error exporting roster data: {e}')
        return f'Error: {str(e)}'


def assign_jersey_numbers_automatically(team) -> int:
    """
    Asigna números de dorsal automáticamente a jugadores sin número
    
    Args:
        team: Team object
    
    Returns:
        Número de dorsales asignados
    """
    try:
        # Obtener jugadores sin número de dorsal
        players_without_jersey = PlayerRole.objects.filter(
            team=team,
            is_active=True,
            jersey_number__isnull=True
        ).order_by('person__last_name', 'person__first_name')
        
        # Obtener números ya asignados
        assigned_numbers = set(PlayerRole.objects.filter(
            team=team,
            is_active=True,
            jersey_number__isnull=False
        ).values_list('jersey_number', flat=True))
        
        # Números disponibles (1-99)
        available_numbers = set(range(1, 100)) - assigned_numbers
        
        assigned_count = 0
        for player in players_without_jersey:
            if available_numbers:
                # Asignar el primer número disponible
                jersey_number = min(available_numbers)
                player.jersey_number = jersey_number
                player.save()
                available_numbers.remove(jersey_number)
                assigned_count += 1
                logger.info(f'Dorsal {jersey_number} asignado a {player.person.full_name}')
        
        logger.info(f'Dorsales asignados automáticamente: {assigned_count}')
        return assigned_count
        
    except Exception as e:
        logger.error(f'Error assigning jersey numbers automatically: {e}')
        return 0


def get_roster_availability(team) -> Dict:
    """
    Obtiene información de disponibilidad de la plantilla
    
    Args:
        team: Team object
    
    Returns:
        Diccionario con información de disponibilidad
    """
    try:
        # Obtener roles activos
        players = PlayerRole.objects.filter(team=team, is_active=True)
        staff = StaffRole.objects.filter(team=team, is_active=True)
        
        # Contar por posición
        position_availability = {}
        for position, display_name in PlayerRole.POSITION_CHOICES:
            count = players.filter(position=position).count()
            position_availability[display_name] = count
        
        # Contar por rol de staff
        role_availability = {}
        for role, display_name in StaffRole.STAFF_ROLES:
            count = staff.filter(role=role).count()
            role_availability[display_name] = count
        
        # Análisis de cobertura
        coverage_analysis = {
            'has_head_coach': staff.filter(role='head_coach').exists(),
            'has_assistant_coach': staff.filter(role='assistant_coach').exists(),
            'has_delegate': staff.filter(role='delegate').exists(),
            'min_players_needed': 6,  # Mínimo para un partido
            'current_players': players.count(),
            'has_sufficient_players': players.count() >= 6,
        }
        
        return {
            'position_availability': position_availability,
            'role_availability': role_availability,
            'coverage_analysis': coverage_analysis,
            'total_players': players.count(),
            'total_staff': staff.count(),
        }
        
    except Exception as e:
        logger.error(f'Error getting roster availability: {e}')
        return {'error': str(e)}


def search_persons_by_criteria(criteria: Dict) -> List[Person]:
    """
    Busca personas por criterios específicos
    
    Args:
        criteria: Diccionario con criterios de búsqueda
    
    Returns:
        Lista de personas que cumplen los criterios
    """
    try:
        queryset = Person.objects.all()
        
        # Filtro por nombre
        if criteria.get('name'):
            queryset = queryset.filter(
                Q(first_name__icontains=criteria['name']) |
                Q(last_name__icontains=criteria['name'])
            )
        
        # Filtro por edad
        if criteria.get('min_age') or criteria.get('max_age'):
            from datetime import date, timedelta
            
            if criteria.get('min_age'):
                max_birth_date = date.today() - timedelta(days=criteria['min_age'] * 365)
                queryset = queryset.filter(birth_date__lte=max_birth_date)
            
            if criteria.get('max_age'):
                min_birth_date = date.today() - timedelta(days=(criteria['max_age'] + 1) * 365)
                queryset = queryset.filter(birth_date__gte=min_birth_date)
        
        # Filtro por rol
        if criteria.get('role') == 'players':
            queryset = queryset.filter(player_roles__isnull=False).distinct()
        elif criteria.get('role') == 'staff':
            queryset = queryset.filter(staff_roles__isnull=False).distinct()
        
        # Filtro por equipo
        if criteria.get('team'):
            queryset = queryset.filter(
                Q(player_roles__team=criteria['team']) |
                Q(staff_roles__team=criteria['team'])
            ).distinct()
        
        # Filtro por posición (solo jugadores)
        if criteria.get('position'):
            queryset = queryset.filter(
                player_roles__position=criteria['position']
            ).distinct()
        
        # Filtro por activo
        if criteria.get('is_active') is not None:
            queryset = queryset.filter(is_active=criteria['is_active'])
        
        return list(queryset)
        
    except Exception as e:
        logger.error(f'Error searching persons by criteria: {e}')
        return []


def get_team_roster_summary(team) -> Dict:
    """
    Obtiene un resumen de la plantilla del equipo
    
    Args:
        team: Team object
    
    Returns:
        Diccionario con resumen de la plantilla
    """
    try:
        players = PlayerRole.objects.filter(team=team, is_active=True)
        staff = StaffRole.objects.filter(team=team, is_active=True)
        
        summary = {
            'team_name': team.name,
            'team_category': team.category.name if team.category else 'Sin categoría',
            'total_people': players.count() + staff.count(),
            'players': {
                'count': players.count(),
                'with_jersey': players.filter(jersey_number__isnull=False).count(),
                'positions': list(players.values_list('position', flat=True).distinct()),
            },
            'staff': {
                'count': staff.count(),
                'roles': list(staff.values_list('role', flat=True).distinct()),
                'has_head_coach': staff.filter(role='head_coach').exists(),
            },
            'last_updated': timezone.now().isoformat(),
        }
        
        return summary
        
    except Exception as e:
        logger.error(f'Error getting team roster summary: {e}')
        return {'error': str(e)}