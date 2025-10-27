from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
import logging

from .models import Person, PlayerRole, StaffRole, PersonManager, PlayerRoleManager, StaffRoleManager

logger = logging.getLogger(__name__)


def person_list(request):
    """Lista de personas con filtros"""
    persons = Person.objects.prefetch_related('player_roles', 'staff_roles').all()
    
    # Filtros
    search_query = request.GET.get('search', '').strip()
    role_filter = request.GET.get('role', '')
    age_min = request.GET.get('age_min')
    age_max = request.GET.get('age_max')
    active_only = request.GET.get('active_only', '0') == '1'
    has_roles = request.GET.get('has_roles', '0') == '1'
    
    # Aplicar filtros
    if search_query:
        persons = persons.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone__icontains=search_query)
        )
    
    if role_filter == 'players':
        persons = persons.filter(player_roles__isnull=False).distinct()
    elif role_filter == 'staff':
        persons = persons.filter(staff_roles__isnull=False).distinct()
    
    if age_min:
        try:
            from datetime import date, timedelta
            max_birth_date = date.today() - timedelta(days=int(age_min) * 365)
            persons = persons.filter(birth_date__lte=max_birth_date)
        except ValueError:
            pass
    
    if age_max:
        try:
            from datetime import date, timedelta
            min_birth_date = date.today() - timedelta(days=(int(age_max) + 1) * 365)
            persons = persons.filter(birth_date__gte=min_birth_date)
        except ValueError:
            pass
    
    if active_only:
        persons = persons.filter(is_active=True)
    
    if has_roles:
        persons = persons.filter(
            Q(player_roles__isnull=False) | Q(staff_roles__isnull=False)
        ).distinct()
    
    # Paginación
    paginator = Paginator(persons, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'role_filter': role_filter,
        'age_min': age_min,
        'age_max': age_max,
        'active_only': active_only,
        'has_roles': has_roles,
    }
    
    return render(request, 'rosters/person_list.html', context)


def person_detail(request, person_id):
    """Detalle de una persona con sus roles"""
    person = get_object_or_404(Person, id=person_id)
    
    # Obtener roles de la persona
    player_roles = person.get_player_roles()
    staff_roles = person.get_staff_roles()
    
    # Obtener equipos donde participa
    teams = person.get_all_active_teams()
    
    # Obtener resumen de roles
    roles_summary = person.get_roles_summary()
    
    context = {
        'person': person,
        'player_roles': player_roles,
        'staff_roles': staff_roles,
        'teams': teams,
        'roles_summary': roles_summary,
    }
    
    return render(request, 'rosters/person_detail.html', context)


def team_roster(request, team_id):
    """Plantilla de un equipo"""
    from videosvoley.videos.models import Team
    team = get_object_or_404(Team, id=team_id)
    
    # Obtener jugadores del equipo
    players = PlayerRole.objects.filter(
        team=team, 
        is_active=True
    ).select_related('person').order_by('jersey_number', 'person__last_name')
    
    # Obtener staff del equipo
    staff = StaffRole.objects.filter(
        team=team, 
        is_active=True
    ).select_related('person').order_by('role', 'person__last_name')
    
    # Estadísticas de la plantilla
    roster_stats = {
        'total_players': players.count(),
        'total_staff': staff.count(),
        'players_with_jersey': players.filter(jersey_number__isnull=False).count(),
        'positions': players.values_list('position', flat=True).distinct(),
        'roles': staff.values_list('role', flat=True).distinct(),
    }
    
    context = {
        'team': team,
        'players': players,
        'staff': staff,
        'roster_stats': roster_stats,
    }
    
    return render(request, 'rosters/team_roster.html', context)


def roster_by_position(request, team_id):
    """Plantilla de un equipo organizada por posición"""
    from videosvoley.videos.models import Team
    team = get_object_or_404(Team, id=team_id)
    
    # Obtener jugadores agrupados por posición
    players_by_position = {}
    for position, display_name in PlayerRole.POSITION_CHOICES:
        players = PlayerRole.objects.filter(
            team=team,
            position=position,
            is_active=True
        ).select_related('person').order_by('jersey_number', 'person__last_name')
        
        if players.exists():
            players_by_position[display_name] = players
    
    # Jugadores sin posición específica
    players_without_position = PlayerRole.objects.filter(
        team=team,
        position='',
        is_active=True
    ).select_related('person').order_by('jersey_number', 'person__last_name')
    
    if players_without_position.exists():
        players_by_position['Sin posición específica'] = players_without_position
    
    context = {
        'team': team,
        'players_by_position': players_by_position,
    }
    
    return render(request, 'rosters/roster_by_position.html', context)


@login_required
def person_statistics(request, person_id):
    """Estadísticas detalladas de una persona (AJAX)"""
    person = get_object_or_404(Person, id=person_id)
    
    try:
        # Obtener roles de la persona
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
        player_stats = {
            'total_teams': player_roles.values('team').distinct().count(),
            'positions': list(player_roles.values_list('position', flat=True).distinct()),
            'jersey_numbers': list(player_roles.filter(jersey_number__isnull=False).values_list('jersey_number', flat=True)),
        }
        
        # Estadísticas de roles de staff
        staff_stats = {
            'total_teams': staff_roles.values('team').distinct().count(),
            'roles': list(staff_roles.values_list('role', flat=True).distinct()),
        }
        
        # Estadísticas por equipo
        teams_stats = []
        for team in person.get_all_active_teams():
            team_player_roles = player_roles.filter(team=team)
            team_staff_roles = staff_roles.filter(team=team)
            
            teams_stats.append({
                'team_name': team.name,
                'team_category': team.category.name if team.category else 'Sin categoría',
                'player_roles': [
                    {
                        'position': role.display_position,
                        'jersey_number': role.jersey_number,
                    }
                    for role in team_player_roles
                ],
                'staff_roles': [
                    {
                        'role': role.display_role,
                    }
                    for role in team_staff_roles
                ],
            })
        
        data = {
            'success': True,
            'stats': stats,
            'player_stats': player_stats,
            'staff_stats': staff_stats,
            'teams_stats': teams_stats,
        }
        
    except Exception as e:
        logger.error(f'Error getting person statistics: {e}')
        data = {
            'success': False,
            'error': str(e)
        }
    
    return JsonResponse(data)


def search_persons(request):
    """Búsqueda de personas (AJAX)"""
    query = request.GET.get('q', '').strip()
    
    if len(query) < 2:
        return JsonResponse({'persons': []})
    
    persons = Person.objects.filter(
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query) |
        Q(email__icontains=query)
    ).select_related('user')[:10]
    
    results = []
    for person in persons:
        results.append({
            'id': person.id,
            'name': person.full_name,
            'email': person.email,
            'age': person.age,
            'is_active': person.is_active,
        })
    
    return JsonResponse({'persons': results})


def roster_export(request, team_id):
    """Exportar plantilla de un equipo"""
    from videosvoley.videos.models import Team
    team = get_object_or_404(Team, id=team_id)
    
    # Obtener datos de la plantilla
    players = PlayerRole.objects.filter(
        team=team, 
        is_active=True
    ).select_related('person').order_by('jersey_number', 'person__last_name')
    
    staff = StaffRole.objects.filter(
        team=team, 
        is_active=True
    ).select_related('person').order_by('role', 'person__last_name')
    
    # Preparar datos para exportación
    export_data = {
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
            }
            for role in players
        ],
        'staff': [
            {
                'name': role.person.full_name,
                'role': role.display_role,
                'age': role.person.age,
            }
            for role in staff
        ],
        'exported_at': timezone.now().isoformat(),
    }
    
    # Retornar como JSON (se puede extender para otros formatos)
    return JsonResponse(export_data, json_dumps_params={'indent': 2})


@login_required
def assign_jersey_number(request, role_id):
    """Asignar número de dorsal a un jugador (AJAX)"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'})
    
    try:
        role = get_object_or_404(PlayerRole, id=role_id)
        jersey_number = request.POST.get('jersey_number')
        
        if jersey_number:
            jersey_number = int(jersey_number)
            if 1 <= jersey_number <= 99:
                # Verificar que el número no esté en uso
                existing = PlayerRole.objects.filter(
                    team=role.team,
                    jersey_number=jersey_number,
                    is_active=True
                ).exclude(pk=role.pk)
                
                if existing.exists():
                    return JsonResponse({
                        'success': False, 
                        'error': f'El número {jersey_number} ya está en uso en {role.team.name}'
                    })
                
                role.jersey_number = jersey_number
                role.save()
                
                return JsonResponse({
                    'success': True,
                    'jersey_number': jersey_number
                })
            else:
                return JsonResponse({
                    'success': False, 
                    'error': 'El número de dorsal debe estar entre 1 y 99'
                })
        else:
            return JsonResponse({
                'success': False, 
                'error': 'Número de dorsal requerido'
            })
            
    except ValueError:
        return JsonResponse({
            'success': False, 
            'error': 'Número de dorsal inválido'
        })
    except Exception as e:
        logger.error(f'Error assigning jersey number: {e}')
        return JsonResponse({
            'success': False, 
            'error': str(e)
        })