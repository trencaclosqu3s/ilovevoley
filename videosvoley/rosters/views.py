"""
Views para la gestión de plantillas y personas.
Migradas desde videos.views para la nueva app rosters.
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Prefetch
from django.http import JsonResponse
from django.conf import settings
from django.views.decorators.http import require_POST
from django.utils import timezone
from datetime import datetime, timedelta
import logging

from .models import Person, PlayerRole, StaffRole
from .forms import PersonForm, PlayerRoleForm, StaffRoleForm

# Importar modelos de otras apps
from videosvoley.teams.models import Team, Club
from videosvoley.content.models import Category

# Configurar logger
logger = logging.getLogger(__name__)


def user_is_approved(user):
    """Verifica si el usuario está aprobado para acceder al contenido"""
    return user.is_approved


def user_is_staff_or_manager(user):
    """Verifica si el usuario es staff o manager para gestionar plantillas"""
    return user.is_staff or user.groups.filter(name='VideoManagers').exists()


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def person_list(request):
    """Vista para mostrar todas las personas registradas"""
    persons = Person.objects.all().prefetch_related('player_roles__team', 'staff_roles__team')
    
    # Filtros
    search_query = request.GET.get('search', '').strip()
    role_filter = request.GET.get('role')
    team_filter = request.GET.get('team')
    show_all = request.GET.get('show_all', '0') == '1'
    
    # Aplicar búsqueda
    if search_query:
        persons = persons.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone__icontains=search_query)
        )
    
    # Aplicar filtro de rol
    if role_filter:
        if role_filter == 'player':
            persons = persons.filter(player_roles__isnull=False).distinct()
        elif role_filter == 'staff':
            persons = persons.filter(staff_roles__isnull=False).distinct()
    
    # Aplicar filtro de equipo
    if team_filter:
        persons = persons.filter(
            Q(player_roles__team_id=team_filter) | Q(staff_roles__team_id=team_filter)
        ).distinct()
    
    # Ordenar por apellido y nombre
    persons = persons.order_by('last_name', 'first_name')
    
    # Paginación
    paginator = Paginator(persons, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Obtener datos para filtros
    teams = Team.objects.filter(is_active=True).order_by('name')
    
    return render(request, 'rosters/person_list.html', {
        'page_obj': page_obj,
        'teams': teams,
        'search_query': search_query,
        'selected_role': role_filter,
        'selected_team': team_filter,
        'show_all': show_all,
    })


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def person_detail(request, person_id):
    """Vista detallada de una persona con sus roles"""
    person = get_object_or_404(Person, id=person_id)
    
    # Obtener roles de la persona
    player_roles = person.player_roles.select_related('team', 'team__category').order_by('team__name')
    staff_roles = person.staff_roles.select_related('team', 'team__category').order_by('team__name')
    
    # Estadísticas de la persona
    total_teams = len(set(list(player_roles.values_list('team_id', flat=True)) + list(staff_roles.values_list('team_id', flat=True))))
    active_roles = player_roles.filter(is_active=True).count() + staff_roles.filter(is_active=True).count()
    
    return render(request, 'rosters/person_detail.html', {
        'person': person,
        'player_roles': player_roles,
        'staff_roles': staff_roles,
        'total_teams': total_teams,
        'active_roles': active_roles,
    })


@login_required
@user_passes_test(user_is_staff_or_manager, login_url='/')
def person_create(request):
    """Vista para crear una nueva persona"""
    if request.method == 'POST':
        form = PersonForm(request.POST)
        if form.is_valid():
            person = form.save()
            messages.success(request, f'Persona "{person.get_full_name()}" creada correctamente')
            return redirect('rosters:person_detail', person_id=person.id)
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = PersonForm()
    
    return render(request, 'rosters/person_form.html', {
        'form': form,
        'title': 'Crear Nueva Persona',
        'submit_text': 'Crear Persona',
    })


@login_required
@user_passes_test(user_is_staff_or_manager, login_url='/')
def person_edit(request, person_id):
    """Vista para editar una persona existente"""
    person = get_object_or_404(Person, id=person_id)
    
    if request.method == 'POST':
        form = PersonForm(request.POST, instance=person)
        if form.is_valid():
            person = form.save()
            messages.success(request, f'Persona "{person.get_full_name()}" actualizada correctamente')
            return redirect('rosters:person_detail', person_id=person.id)
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = PersonForm(instance=person)
    
    return render(request, 'rosters/person_form.html', {
        'form': form,
        'person': person,
        'title': f'Editar {person.get_full_name()}',
        'submit_text': 'Actualizar Persona',
    })


@login_required
@user_passes_test(user_is_staff_or_manager, login_url='/')
def player_role_create(request, person_id):
    """Vista para crear un rol de jugador"""
    person = get_object_or_404(Person, id=person_id)
    
    if request.method == 'POST':
        form = PlayerRoleForm(request.POST)
        if form.is_valid():
            role = form.save(commit=False)
            role.person = person
            role.save()
            messages.success(request, f'Rol de jugador creado para {person.get_full_name()}')
            return redirect('rosters:person_detail', person_id=person.id)
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = PlayerRoleForm()
    
    return render(request, 'rosters/role_form.html', {
        'form': form,
        'person': person,
        'role_type': 'player',
        'title': f'Crear Rol de Jugador - {person.get_full_name()}',
        'submit_text': 'Crear Rol',
    })


@login_required
@user_passes_test(user_is_staff_or_manager, login_url='/')
def staff_role_create(request, person_id):
    """Vista para crear un rol de staff"""
    person = get_object_or_404(Person, id=person_id)
    
    if request.method == 'POST':
        form = StaffRoleForm(request.POST)
        if form.is_valid():
            role = form.save(commit=False)
            role.person = person
            role.save()
            messages.success(request, f'Rol de staff creado para {person.get_full_name()}')
            return redirect('rosters:person_detail', person_id=person.id)
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = StaffRoleForm()
    
    return render(request, 'rosters/role_form.html', {
        'form': form,
        'person': person,
        'role_type': 'staff',
        'title': f'Crear Rol de Staff - {person.get_full_name()}',
        'submit_text': 'Crear Rol',
    })


@login_required
@user_passes_test(user_is_staff_or_manager, login_url='/')
def player_role_edit(request, role_id):
    """Vista para editar un rol de jugador"""
    role = get_object_or_404(PlayerRole, id=role_id)
    
    if request.method == 'POST':
        form = PlayerRoleForm(request.POST, instance=role)
        if form.is_valid():
            role = form.save()
            messages.success(request, f'Rol de jugador actualizado para {role.person.get_full_name()}')
            return redirect('rosters:person_detail', person_id=role.person.id)
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = PlayerRoleForm(instance=role)
    
    return render(request, 'rosters/role_form.html', {
        'form': form,
        'person': role.person,
        'role': role,
        'role_type': 'player',
        'title': f'Editar Rol de Jugador - {role.person.get_full_name()}',
        'submit_text': 'Actualizar Rol',
    })


@login_required
@user_passes_test(user_is_staff_or_manager, login_url='/')
def staff_role_edit(request, role_id):
    """Vista para editar un rol de staff"""
    role = get_object_or_404(StaffRole, id=role_id)
    
    if request.method == 'POST':
        form = StaffRoleForm(request.POST, instance=role)
        if form.is_valid():
            role = form.save()
            messages.success(request, f'Rol de staff actualizado para {role.person.get_full_name()}')
            return redirect('rosters:person_detail', person_id=role.person.id)
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = StaffRoleForm(instance=role)
    
    return render(request, 'rosters/role_form.html', {
        'form': form,
        'person': role.person,
        'role': role,
        'role_type': 'staff',
        'title': f'Editar Rol de Staff - {role.person.get_full_name()}',
        'submit_text': 'Actualizar Rol',
    })


@login_required
@user_passes_test(user_is_staff_or_manager, login_url='/')
@require_POST
def player_role_toggle_active(request, role_id):
    """Vista AJAX para activar/desactivar un rol de jugador"""
    try:
        role = PlayerRole.objects.get(id=role_id)
        role.is_active = not role.is_active
        role.save()
        
        status = 'activado' if role.is_active else 'desactivado'
        return JsonResponse({
            'success': True,
            'message': f'Rol de jugador {status} correctamente',
            'is_active': role.is_active
        })
    except PlayerRole.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Rol de jugador no encontrado'
        }, status=404)
    except Exception as e:
        logger.error(f"Error toggling player role {role_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Error interno del servidor'
        }, status=500)


@login_required
@user_passes_test(user_is_staff_or_manager, login_url='/')
@require_POST
def staff_role_toggle_active(request, role_id):
    """Vista AJAX para activar/desactivar un rol de staff"""
    try:
        role = StaffRole.objects.get(id=role_id)
        role.is_active = not role.is_active
        role.save()
        
        status = 'activado' if role.is_active else 'desactivado'
        return JsonResponse({
            'success': True,
            'message': f'Rol de staff {status} correctamente',
            'is_active': role.is_active
        })
    except StaffRole.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Rol de staff no encontrado'
        }, status=404)
    except Exception as e:
        logger.error(f"Error toggling staff role {role_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Error interno del servidor'
        }, status=500)


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
    
    return render(request, 'rosters/roster_overview.html', {
        'teams_by_category': teams_by_category,
        'total_teams': total_teams,
        'total_players': total_players,
        'total_staff': total_staff,
        'club_team_name': CLUB_TEAM_NAME,
    })


@login_required
def ajax_search_persons(request):
    """Vista AJAX para buscar personas con autocompletado"""
    query = request.GET.get('q', '').strip()
    
    if len(query) < 2:
        return JsonResponse({'persons': []})
    
    # Buscar personas existentes
    persons_query = Person.objects.filter(
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query) |
        Q(email__icontains=query)
    )
    
    # Limitar a 10 resultados
    persons = persons_query.order_by('last_name', 'first_name')[:10]
    
    # Formatear respuesta
    persons_data = []
    for person in persons:
        persons_data.append({
            'id': person.id,
            'name': person.get_full_name(),
            'email': person.email,
            'phone': person.phone,
        })
    
    return JsonResponse({'persons': persons_data})


@login_required
def ajax_persons_by_team(request):
    """Vista AJAX para obtener personas de un equipo específico"""
    team_id = request.GET.get('team_id')
    role_type = request.GET.get('role_type', 'all')  # 'player', 'staff', 'all'
    
    if not team_id:
        return JsonResponse({'persons': []})
    
    try:
        team = Team.objects.get(id=team_id)
        
        if role_type == 'player':
            roles = team.player_roles.select_related('person').filter(is_active=True)
        elif role_type == 'staff':
            roles = team.staff_roles.select_related('person').filter(is_active=True)
        else:  # all
            player_roles = team.player_roles.select_related('person').filter(is_active=True)
            staff_roles = team.staff_roles.select_related('person').filter(is_active=True)
            roles = list(player_roles) + list(staff_roles)
        
        # Formatear respuesta
        persons_data = []
        for role in roles:
            if hasattr(role, 'person'):
                person = role.person
                persons_data.append({
                    'id': person.id,
                    'name': person.get_full_name(),
                    'email': person.email,
                    'phone': person.phone,
                    'role_type': 'player' if hasattr(role, 'position') else 'staff',
                    'position': getattr(role, 'position', None),
                    'role': getattr(role, 'role', None),
                })
        
        return JsonResponse({'persons': persons_data})
        
    except Team.DoesNotExist:
        return JsonResponse({'persons': []})


@login_required
@user_passes_test(user_is_staff_or_manager, login_url='/')
def ajax_create_person(request):
    """Vista AJAX para crear una nueva persona"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)
    
    try:
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        
        if not first_name or not last_name:
            return JsonResponse({'success': False, 'error': 'Nombre y apellido son requeridos'})
        
        # Verificar si ya existe una persona con el mismo nombre y apellido
        existing_person = Person.objects.filter(
            first_name__iexact=first_name,
            last_name__iexact=last_name
        ).first()
        
        if existing_person:
            return JsonResponse({
                'success': False,
                'error': f'Ya existe una persona llamada "{first_name} {last_name}"',
                'existing_person': {
                    'id': existing_person.id,
                    'name': existing_person.get_full_name(),
                    'email': existing_person.email
                }
            })
        
        # Crear nueva persona
        new_person = Person.objects.create(
            first_name=first_name,
            last_name=last_name,
            email=email if email else None,
            phone=phone if phone else None
        )
        
        logger.info(f"Persona creada: {new_person.get_full_name()} por usuario {request.user.username}")
        
        return JsonResponse({
            'success': True,
            'message': f'Persona "{new_person.get_full_name()}" creada correctamente',
            'person': {
                'id': new_person.id,
                'name': new_person.get_full_name(),
                'email': new_person.email,
                'phone': new_person.phone,
            }
        })
        
    except Exception as e:
        logger.error(f"Error creando persona: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Error interno del servidor'
        }, status=500)