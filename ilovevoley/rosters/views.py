import base64
import logging
import uuid

from django.contrib import messages
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ilovevoley.core.mixins import get_club_team_name_filter
from ilovevoley.core.models import Category, Season
from ilovevoley.core.season_utils import resolve_season_filter
from ilovevoley.core.tenant_utils import tenant_access_required
from ilovevoley.teams.models import Team
from .forms import PersonForm, PlayerRoleForm, StaffRoleForm
from .models import Person, PlayerRole, StaffRole

logger = logging.getLogger(__name__)


@tenant_access_required()
def roster_overview(request):
    """Vista general de todas las plantillas del club"""
    # Obtener categorías del usuario para filtrar
    user_categories = request.user.preferred_categories.all() if request.user.preferred_categories.exists() else Category.objects.filter(is_active=True)

    # Query base para equipos del club
    teams_query = Team.objects.select_related("category", "club").prefetch_related(
        "player_roles__person", "staff_roles__person"
    ).filter(is_active=True).filter(get_club_team_name_filter(request.tenant))
    
    # Filtrar por categorías preferidas del usuario
    category_filter = request.GET.get("category")
    show_all = request.GET.get("show_all", "0") == "1"
    
    if not show_all and not category_filter:
        teams_query = teams_query.filter(category__in=user_categories)
    elif category_filter:
        teams_query = teams_query.filter(category_id=category_filter)
    
    teams = teams_query.order_by("category__name", "name")

    # Temporada a mostrar (activa por defecto)
    season_filter, selected_season = resolve_season_filter(request)

    # Estadísticas generales
    total_stats = {
        "total_teams": teams.count(),
        "total_players": 0,
        "total_staff": 0,
        "teams_with_good_roster": 0,  # Equipos con 8+ jugadores (buen número para rotaciones)
        "categories_summary": {},
    }
    
    for team in teams:
        # Usar nueva estructura Person-Role evaluada en memoria para evitar N+1 queries
        active_player_roles = [
            r for r in team.player_roles.all()
            if r.is_active and (season_filter is None or r.season_id == season_filter.pk)
        ]
        active_staff_roles = [
            r for r in team.staff_roles.all()
            if r.is_active and (season_filter is None or r.season_id == season_filter.pk)
        ]
        
        team.active_players_count = len(active_player_roles)
        team.active_staff_count = len(active_staff_roles)
        team.has_good_roster = team.active_players_count >= 8  # Suficientes para rotaciones
        
        total_stats["total_players"] += team.active_players_count
        total_stats["total_staff"] += team.active_staff_count
        
        if team.has_good_roster:
            total_stats["teams_with_good_roster"] += 1
        
        # Estadísticas por categoría
        cat_name = team.category.name if team.category else "Sin categoría"
        if cat_name not in total_stats["categories_summary"]:
            total_stats["categories_summary"][cat_name] = {
                "teams": 0, "players": 0, "staff": 0
            }
        
        total_stats["categories_summary"][cat_name]["teams"] += 1
        total_stats["categories_summary"][cat_name]["players"] += team.active_players_count
        total_stats["categories_summary"][cat_name]["staff"] += team.active_staff_count
    
    # Obtener categorías para el filtro
    categories = Category.objects.filter(is_active=True).order_by("name")
    
    context = {
        "teams": teams,
        "total_stats": total_stats,
        "categories": categories,
        "seasons": Season.objects.all(),
        "selected_season": selected_season,
        "season_filtered": "season" in request.GET,
        "selected_category": category_filter,
        "show_all": show_all,
        "user_categories": user_categories,
    }
    
    return render(request, "rosters/roster_overview.html", context)


@tenant_access_required()
def person_list(request):
    """Vista de listado de personas del club"""
    # Obtener todas las personas activas con sus roles
    people = Person.objects.filter(is_active=True).prefetch_related(
        'player_roles__team__category',
        'staff_roles__team__category'
    ).order_by('last_name', 'first_name')
    
    # Filtros
    search = request.GET.get('search', '').strip()
    role_type = request.GET.get('role_type', '')  # 'player', 'staff', o ''
    
    if search:
        people = people.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search)
        )
    
    if role_type == 'player':
        people = people.filter(player_roles__is_active=True).distinct()
    elif role_type == 'staff':
        people = people.filter(staff_roles__is_active=True).distinct()
    
    # Paginación
    paginator = Paginator(people, 24)  # 24 personas por página
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Enriquecer con info de roles
    for person in page_obj:
        person.active_player_roles = person.get_player_roles()
        person.active_staff_roles = person.get_staff_roles()
    
    context = {
        'page_obj': page_obj,
        'search': search,
        'role_type': role_type,
    }
    
    return render(request, 'rosters/person_list.html', context)


@tenant_access_required()
def person_detail(request, person_id):
    """Vista de detalle de una persona"""
    person = get_object_or_404(
        Person.objects.prefetch_related(
            'player_roles__team__category',
            'staff_roles__team__category'
        ),
        id=person_id
    )
    
    # Obtener roles activos e inactivos
    player_roles = person.player_roles.select_related('team__category').order_by('-is_active', 'team__name')
    staff_roles = person.staff_roles.select_related('team__category').order_by('-is_active', 'team__name')
    
    # Verificar permisos de edición
    can_edit = request.user.can_edit_person(person)
    
    context = {
        'person': person,
        'player_roles': player_roles,
        'staff_roles': staff_roles,
        'can_edit': can_edit,
    }
    
    return render(request, 'rosters/person_detail.html', context)


@tenant_access_required()
def person_create(request):
    """Vista para crear una nueva persona"""
    if request.method == 'POST':
        form = PersonForm(request.POST, request.FILES)
        
        if form.is_valid():
            person = form.save(commit=False)
            
            # Procesar imagen recortada si está presente
            cropped_photo_data = request.POST.get('cropped_photo_data')
            if cropped_photo_data and cropped_photo_data.startswith('data:image'):
                try:
                    # Extraer datos base64
                    format_str, imgstr = cropped_photo_data.split(';base64,')
                    ext = format_str.split('/')[-1]
                    
                    # Decodificar imagen
                    data = base64.b64decode(imgstr)
                    
                    # Crear archivo temporal
                    photo_file = ContentFile(data, name=f"person.{ext}")
                    
                    # Asignar la foto recortada (se sanea en Person.save)
                    person.photo = photo_file
                    
                except Exception as e:
                    logger.error(f'Error al procesar la imagen recortada: {str(e)}')
                    messages.error(request, f'Error al procesar la imagen recortada: {str(e)}')
                    return render(request, 'rosters/person_form.html', {
                        'form': form,
                        'title': 'Agregar Nueva Persona',
                        'submit_text': 'Crear Persona',
                    })
            
            # Si el usuario no tiene un person vinculado, vincular este
            if not hasattr(request.user, 'person'):
                person.user = request.user
            
            person.save()
            messages.success(request, '¡Persona creada exitosamente! Ahora puedes agregar roles de jugador o staff.')
            return redirect('rosters:person_detail', person_id=person.id)
    else:
        form = PersonForm()
    
    context = {
        'form': form,
        'title': 'Agregar Nueva Persona',
        'submit_text': 'Crear Persona',
    }
    
    return render(request, 'rosters/person_form.html', context)


@tenant_access_required()
def person_edit(request, person_id):
    """Vista para editar una persona existente"""
    person = get_object_or_404(Person, id=person_id)
    
    # Verificar permisos
    can_edit = request.user.can_edit_person(person)
    
    if not can_edit:
        messages.error(request, 'No tienes permisos para editar esta persona.')
        return redirect('rosters:person_detail', person_id=person.id)
    
    if request.method == 'POST':
        form = PersonForm(request.POST, request.FILES, instance=person)
        
        if form.is_valid():
            # Procesar imagen recortada si está presente
            cropped_photo_data = request.POST.get('cropped_photo_data')
            if cropped_photo_data and cropped_photo_data.startswith('data:image'):
                try:
                    # Extraer datos base64
                    format_str, imgstr = cropped_photo_data.split(';base64,')
                    ext = format_str.split('/')[-1]
                    
                    # Decodificar imagen
                    data = base64.b64decode(imgstr)
                    
                    # Crear archivo
                    photo_file = ContentFile(data, name=f"person.{ext}")
                    
                    # Asignar la imagen recortada al person (se sanea en Person.save)
                    person.photo = photo_file
                    
                except Exception as e:
                    logger.error(f'Error al procesar la imagen recortada: {str(e)}')
                    messages.error(request, f'Error al procesar la imagen recortada: {str(e)}')
                    return render(request, 'rosters/person_form.html', {
                        'form': form,
                        'person': person,
                        'title': f'Editar {person.full_name}',
                        'submit_text': 'Guardar Cambios',
                    })
            
            form.save()
            messages.success(request, '¡Información actualizada correctamente!')
            return redirect('rosters:person_detail', person_id=person.id)
        else:
            messages.error(request, 'Por favor corrige los errores en el formulario.')
    else:
        form = PersonForm(instance=person)
    
    context = {
        'form': form,
        'person': person,
        'title': f'Editar {person.full_name}',
        'submit_text': 'Guardar Cambios',
    }
    
    return render(request, 'rosters/person_form.html', context)


@tenant_access_required()
def player_role_create(request, person_id):
    """Vista para agregar un rol de jugador a una persona"""
    person = get_object_or_404(Person, id=person_id)
    
    # Verificar permisos
    can_edit = request.user.is_staff or request.user == person.user
    if not can_edit:
        messages.error(request, 'No tienes permisos para agregar roles a esta persona.')
        return redirect('rosters:person_detail', person_id=person.id)
    
    if request.method == 'POST':
        form = PlayerRoleForm(request.POST, person=person, organization=request.tenant)
        if form.is_valid():
            player_role = form.save(commit=False)
            player_role.person = person
            player_role.save()
            messages.success(request, f'¡Rol de jugador agregado en {player_role.team.name}!')
            return redirect('rosters:person_detail', person_id=person.id)
    else:
        form = PlayerRoleForm(person=person, organization=request.tenant)
    
    context = {
        'form': form,
        'person': person,
        'title': f'Agregar Rol de Jugador - {person.full_name}',
        'submit_text': 'Agregar Rol',
        'role_type': 'player',
    }
    
    return render(request, 'rosters/role_form.html', context)


@tenant_access_required()
def staff_role_create(request, person_id):
    """Vista para agregar un rol de staff a una persona"""
    person = get_object_or_404(Person, id=person_id)
    
    # Verificar permisos
    can_edit = request.user.is_staff or request.user == person.user
    if not can_edit:
        messages.error(request, 'No tienes permisos para agregar roles a esta persona.')
        return redirect('rosters:person_detail', person_id=person.id)
    
    if request.method == 'POST':
        form = StaffRoleForm(request.POST, person=person, organization=request.tenant)
        if form.is_valid():
            staff_role = form.save(commit=False)
            staff_role.person = person
            staff_role.save()
            messages.success(request, f'¡Rol de staff agregado en {staff_role.team.name}!')
            return redirect('rosters:person_detail', person_id=person.id)
    else:
        form = StaffRoleForm(person=person, organization=request.tenant)
    
    context = {
        'form': form,
        'person': person,
        'title': f'Agregar Rol de Staff - {person.full_name}',
        'submit_text': 'Agregar Rol',
        'role_type': 'staff',
    }
    
    return render(request, 'rosters/role_form.html', context)


@tenant_access_required()
def player_role_edit(request, role_id):
    """Vista para editar un rol de jugador"""
    player_role = get_object_or_404(PlayerRole.objects.select_related('person', 'team'), id=role_id)
    
    # Verificar permisos
    can_edit = request.user.is_staff or request.user == player_role.person.user
    if not can_edit:
        messages.error(request, 'No tienes permisos para editar este rol.')
        return redirect('rosters:person_detail', person_id=player_role.person.id)
    
    if request.method == 'POST':
        form = PlayerRoleForm(request.POST, instance=player_role, person=player_role.person, organization=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, '¡Rol actualizado correctamente!')
            return redirect('rosters:person_detail', person_id=player_role.person.id)
    else:
        form = PlayerRoleForm(instance=player_role, person=player_role.person, organization=request.tenant)
    
    context = {
        'form': form,
        'person': player_role.person,
        'player_role': player_role,
        'title': f'Editar Rol de Jugador - {player_role.person.full_name}',
        'submit_text': 'Guardar Cambios',
        'role_type': 'player',
    }
    
    return render(request, 'rosters/role_form.html', context)


@tenant_access_required()
def staff_role_edit(request, role_id):
    """Vista para editar un rol de staff"""
    staff_role = get_object_or_404(StaffRole.objects.select_related('person', 'team'), id=role_id)
    
    # Verificar permisos
    can_edit = request.user.is_staff or request.user == staff_role.person.user
    if not can_edit:
        messages.error(request, 'No tienes permisos para editar este rol.')
        return redirect('rosters:person_detail', person_id=staff_role.person.id)
    
    if request.method == 'POST':
        form = StaffRoleForm(request.POST, instance=staff_role, person=staff_role.person, organization=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, '¡Rol actualizado correctamente!')
            return redirect('rosters:person_detail', person_id=staff_role.person.id)
    else:
        form = StaffRoleForm(instance=staff_role, person=staff_role.person, organization=request.tenant)
    
    context = {
        'form': form,
        'person': staff_role.person,
        'staff_role': staff_role,
        'title': f'Editar Rol de Staff - {staff_role.person.full_name}',
        'submit_text': 'Guardar Cambios',
        'role_type': 'staff',
    }
    
    return render(request, 'rosters/role_form.html', context)


@tenant_access_required()
@require_POST
def player_role_toggle_active(request, role_id):
    """Vista AJAX para activar/desactivar rol de jugador"""
    player_role = get_object_or_404(PlayerRole, id=role_id)
    
    # Verificar permisos
    can_edit = request.user.is_staff or request.user == player_role.person.user
    if not can_edit:
        return JsonResponse({'success': False, 'error': 'Sin permisos'}, status=403)
    
    player_role.is_active = not player_role.is_active
    player_role.save()
    
    status = 'activado' if player_role.is_active else 'desactivado'
    messages.success(request, f'Rol de jugador {status} correctamente.')
    
    return JsonResponse({'success': True, 'is_active': player_role.is_active})


@tenant_access_required()
@require_POST
def staff_role_toggle_active(request, role_id):
    """Vista AJAX para activar/desactivar rol de staff"""
    staff_role = get_object_or_404(StaffRole, id=role_id)
    
    # Verificar permisos
    can_edit = request.user.is_staff or request.user == staff_role.person.user
    if not can_edit:
        return JsonResponse({'success': False, 'error': 'Sin permisos'}, status=403)
    
    staff_role.is_active = not staff_role.is_active
    staff_role.save()
    
    status = 'activado' if staff_role.is_active else 'desactivado'
    messages.success(request, f'Rol de staff {status} correctamente.')
    
    return JsonResponse({'success': True, 'is_active': staff_role.is_active})


__all__ = [
    'roster_overview',
    'person_list',
    'person_detail',
    'person_create',
    'person_edit',
    'player_role_create',
    'staff_role_create',
    'player_role_edit',
    'staff_role_edit',
    'player_role_toggle_active',
    'staff_role_toggle_active',
]
