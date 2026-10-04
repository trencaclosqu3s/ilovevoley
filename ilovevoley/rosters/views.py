import logging

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Prefetch, Q
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from ilovevoley.core.image_utils import InvalidImageError, decode_cropped_image
from ilovevoley.core.models import Category, Season
from ilovevoley.core.season_utils import resolve_season_filter
from ilovevoley.core.tenancy import get_tenant_object_or_404
from ilovevoley.core.tenant_utils import tenant_access_required
from ilovevoley.competitions.models import MatchLineup
from ilovevoley.competitions.services.lineups import get_player_season_stats
from ilovevoley.teams.models import Team
from .forms import PersonForm, PlayerRoleForm, StaffRoleForm
from .models import Person, PlayerRole, StaffRole

logger = logging.getLogger(__name__)


@tenant_access_required()
def roster_overview(request):
    """Vista general de todas las plantillas del club"""
    # Obtener categorías del usuario para filtrar
    user_categories = request.user.preferred_categories_for(request.tenant)
    if not user_categories.exists():
        user_categories = Category.objects.filter(is_active=True)

    # Temporada a mostrar (activa por defecto)
    season_filter, selected_season = resolve_season_filter(request)

    role_filter = {"is_active": True}
    if season_filter is not None:
        role_filter["season"] = season_filter

    # Query base para equipos del club; los roles se prefetchean ya filtrados
    teams_query = Team.objects.select_related("category", "club").prefetch_related(
        Prefetch("player_roles", queryset=PlayerRole.objects.filter(**role_filter).select_related("person")),
        Prefetch("staff_roles", queryset=StaffRole.objects.filter(**role_filter).select_related("person")),
    ).filter(is_active=True).for_tenant(request.tenant)
    
    # Filtrar por categorías preferidas del usuario
    category_filter = request.GET.get("category")
    show_all = request.GET.get("show_all", "0") == "1"
    
    if not show_all and not category_filter:
        teams_query = teams_query.filter(category__in=user_categories)
    elif category_filter:
        teams_query = teams_query.filter(category_id=category_filter)
    
    teams = teams_query.order_by("category__name", "name")

    # Estadísticas generales
    total_stats = {
        "total_teams": len(teams),
        "total_players": 0,
        "total_staff": 0,
        "teams_with_good_roster": 0,  # Equipos con 8+ jugadores (buen número para rotaciones)
        "categories_summary": {},
    }
    
    for team in teams:
        active_player_roles = team.player_roles.all()
        active_staff_roles = team.staff_roles.all()
        
        team.active_players_count = len(active_player_roles)
        team.active_staff_count = len(active_staff_roles)
        team.has_good_roster = team.active_players_count >= 8  # Suficientes para rotaciones
        
        total_stats["total_players"] += team.active_players_count
        total_stats["total_staff"] += team.active_staff_count
        
        if team.has_good_roster:
            total_stats["teams_with_good_roster"] += 1
        
        # Estadísticas por categoría
        cat_name = team.category.name if team.category else _("Sin categoría")
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
    # Solo fichas del club del tenant activo
    people = Person.objects.for_tenant(request.tenant).filter(
        is_active=True,
    ).prefetch_related(
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
    
    # Enriquecer con info de roles, solo de equipos del club del tenant
    tenant_teams = Team.objects.for_tenant(request.tenant)
    for person in page_obj:
        person.active_player_roles = person.get_player_roles().filter(team__in=tenant_teams)
        person.active_staff_roles = person.get_staff_roles().filter(team__in=tenant_teams)
    
    context = {
        'page_obj': page_obj,
        'search': search,
        'role_type': role_type,
    }
    
    return render(request, 'rosters/person_list.html', context)


@tenant_access_required()
def my_profile(request):
    """Trayectoria del propio usuario: sus roles en todos los clubes, por temporada.

    No filtra por tenant: la ficha vinculada puede pertenecer a otro club y
    el usuario solo ve sus propios datos (nunca recibe un id por URL).
    """
    person = Person.objects.filter(user=request.user).first()
    if person is None:
        raise Http404

    by_season = {}
    for kind, model in (('player_roles', PlayerRole), ('staff_roles', StaffRole)):
        roles = model.objects.filter(person=person).select_related('team__category', 'team__club', 'season')
        for role in roles.order_by('team__name'):
            by_season.setdefault(role.season, {'season': role.season, 'player_roles': [], 'staff_roles': []})[kind].append(role)
    seasons = sorted(by_season.values(), key=lambda s: s['season'].start_year, reverse=True)

    return render(request, 'rosters/my_profile.html', {
        'person': person,
        'seasons': seasons,
        'in_current_tenant': person.organization_id == request.tenant.id,
    })


@tenant_access_required()
def person_detail(request, person_id):
    """Vista de detalle de una persona"""
    person = get_tenant_object_or_404(
        Person.objects.select_related('organization', 'user').prefetch_related(
            'player_roles__team__category',
            'staff_roles__team__category'
        ),
        request.tenant, user=request.user, id=person_id,
    )
    
    # Roles visibles solo en equipos del club del tenant
    tenant_teams = Team.objects.for_tenant(request.tenant)
    player_roles = person.player_roles.filter(team__in=tenant_teams).select_related('team__category').order_by('-is_active', 'team__name')
    staff_roles = person.staff_roles.filter(team__in=tenant_teams).select_related('team__category').order_by('-is_active', 'team__name')

    # Verificar permisos de edición
    can_edit = request.user.can_edit_person(person, request.tenant)

    # Histórico de actas: temporadas con roles o con partidos registrados
    person_lineups = MatchLineup.objects.filter(person=person, team__in=tenant_teams).exclude(match__status='withdrawn')
    lineup_season_ids = set(person_lineups.values_list('match__league__season_id', flat=True))
    season_ids = set(player_roles.values_list('season_id', flat=True)) | lineup_season_ids
    season_ids.discard(None)
    seasons = Season.objects.filter(pk__in=season_ids).order_by('-start_year')

    stat_season = _resolve_person_stat_season(request, seasons)
    player_stats = get_player_season_stats(person, stat_season, tenant_teams) if person_lineups.exists() else None

    context = {
        'person': person,
        'player_roles': player_roles,
        'staff_roles': staff_roles,
        'can_edit': can_edit,
        'seasons': seasons,
        'stat_season': stat_season,
        'player_stats': player_stats,
    }

    return render(request, 'rosters/person_detail.html', context)


def _resolve_person_stat_season(request, seasons):
    """Temporada a mostrar en las estadísticas del deportista.

    ``?season=<id>`` la fija; ``?season=`` (vacío) agrega todas. Sin parámetro
    se usa la temporada activa si el deportista tiene datos en ella, y si no la
    más reciente.
    """
    if 'season' in request.GET:
        raw = request.GET['season']
        if raw == '':
            return None
        if raw.isdigit():
            return seasons.filter(pk=int(raw)).first() or seasons.first()
        return seasons.first()
    current = Season.objects.current()
    if current is not None and seasons.filter(pk=current.pk).exists():
        return current
    return seasons.first()


@tenant_access_required(manager=True)
def person_create(request):
    """Vista para crear una nueva persona"""
    if request.method == 'POST':
        form = PersonForm(request.POST, request.FILES, organization=request.tenant)
        
        if form.is_valid():
            person = form.save(commit=False)
            person.organization = request.tenant
            
            # Procesar imagen recortada si está presente
            cropped_photo_data = request.POST.get('cropped_photo_data')
            if cropped_photo_data:
                try:
                    person.photo = decode_cropped_image(cropped_photo_data)
                except InvalidImageError as e:
                    logger.warning(f'Imagen recortada rechazada: {e}')
                    messages.error(request, str(e))
                    return render(request, 'rosters/person_form.html', {
                        'form': form,
                        'title': _('Agregar Nueva Persona'),
                        'submit_text': _('Crear Persona'),
                    })
            
            # Si el usuario no tiene un person vinculado, vincular este
            if not hasattr(request.user, 'person'):
                person.user = request.user
            
            person.save()
            messages.success(request, _('¡Persona creada exitosamente! Ahora puedes agregar roles de jugador o staff.'))
            return redirect('rosters:person_detail', person_id=person.id)
    else:
        form = PersonForm()
    
    context = {
        'form': form,
        'title': _('Agregar Nueva Persona'),
        'submit_text': _('Crear Persona'),
    }
    
    return render(request, 'rosters/person_form.html', context)


@tenant_access_required()
def person_edit(request, person_id):
    """Vista para editar una persona existente"""
    person = get_tenant_object_or_404(
        Person.objects, request.tenant, user=request.user, id=person_id,
    )
    
    # Verificar permisos
    can_edit = request.user.can_edit_person(person, request.tenant)
    
    if not can_edit:
        messages.error(request, _('No tienes permisos para editar esta persona.'))
        return redirect('rosters:person_detail', person_id=person.id)
    
    if request.method == 'POST':
        form = PersonForm(
            request.POST, request.FILES, instance=person, organization=request.tenant,
        )
        
        if form.is_valid():
            # PersonForm no expone organization, pero se reafirma el tenant para
            # que un POST manipulado no pueda reasignar la ficha de club.
            person.organization = request.tenant

            # Procesar imagen recortada si está presente
            cropped_photo_data = request.POST.get('cropped_photo_data')
            if cropped_photo_data:
                try:
                    person.photo = decode_cropped_image(cropped_photo_data)
                except InvalidImageError as e:
                    logger.warning(f'Imagen recortada rechazada: {e}')
                    messages.error(request, str(e))
                    return render(request, 'rosters/person_form.html', {
                        'form': form,
                        'person': person,
                        'title': _('Editar %(name)s') % {'name': person.full_name},
                        'submit_text': _('Guardar Cambios'),
                    })
            
            form.save()
            messages.success(request, _('¡Información actualizada correctamente!'))
            return redirect('rosters:person_detail', person_id=person.id)
        else:
            messages.error(request, _('Por favor corrige los errores en el formulario.'))
    else:
        form = PersonForm(instance=person)
    
    context = {
        'form': form,
        'person': person,
        'title': _('Editar %(name)s') % {'name': person.full_name},
        'submit_text': _('Guardar Cambios'),
    }
    
    return render(request, 'rosters/person_form.html', context)


@tenant_access_required(manager=True)
def player_role_create(request, person_id):
    """Vista para agregar un rol de jugador a una persona"""
    person = get_tenant_object_or_404(
        Person.objects, request.tenant, user=request.user, id=person_id,
    )
    
    # Verificar permisos
    can_edit = request.user.can_edit_person(person, request.tenant)
    if not can_edit:
        messages.error(request, _('No tienes permisos para agregar roles a esta persona.'))
        return redirect('rosters:person_detail', person_id=person.id)
    
    if request.method == 'POST':
        form = PlayerRoleForm(request.POST, person=person, organization=request.tenant)
        if form.is_valid():
            player_role = form.save(commit=False)
            player_role.person = person
            player_role.save()
            messages.success(request, _('¡Rol de jugador agregado en %(team)s!') % {'team': player_role.team.name})
            return redirect('rosters:person_detail', person_id=person.id)
    else:
        form = PlayerRoleForm(person=person, organization=request.tenant)
    
    context = {
        'form': form,
        'person': person,
        'title': _('Agregar Rol de Jugador - %(name)s') % {'name': person.full_name},
        'submit_text': _('Agregar Rol'),
        'role_type': 'player',
    }
    
    return render(request, 'rosters/role_form.html', context)


@tenant_access_required(manager=True)
def staff_role_create(request, person_id):
    """Vista para agregar un rol de staff a una persona"""
    person = get_tenant_object_or_404(
        Person.objects, request.tenant, user=request.user, id=person_id,
    )
    
    # Verificar permisos
    can_edit = request.user.can_edit_person(person, request.tenant)
    if not can_edit:
        messages.error(request, _('No tienes permisos para agregar roles a esta persona.'))
        return redirect('rosters:person_detail', person_id=person.id)
    
    if request.method == 'POST':
        form = StaffRoleForm(request.POST, person=person, organization=request.tenant)
        if form.is_valid():
            staff_role = form.save(commit=False)
            staff_role.person = person
            staff_role.save()
            messages.success(request, _('¡Rol de staff agregado en %(team)s!') % {'team': staff_role.team.name})
            return redirect('rosters:person_detail', person_id=person.id)
    else:
        form = StaffRoleForm(person=person, organization=request.tenant)
    
    context = {
        'form': form,
        'person': person,
        'title': _('Agregar Rol de Staff - %(name)s') % {'name': person.full_name},
        'submit_text': _('Agregar Rol'),
        'role_type': 'staff',
    }
    
    return render(request, 'rosters/role_form.html', context)


@tenant_access_required(manager=True)
def player_role_edit(request, role_id):
    """Vista para editar un rol de jugador"""
    player_role = get_tenant_object_or_404(
        PlayerRole.objects.select_related('person', 'team'),
        request.tenant, user=request.user, id=role_id,
    )
    
    # Verificar permisos
    can_edit = request.user.can_edit_person(player_role.person, request.tenant)
    if not can_edit:
        messages.error(request, _('No tienes permisos para editar este rol.'))
        return redirect('rosters:person_detail', person_id=player_role.person.id)
    
    if request.method == 'POST':
        form = PlayerRoleForm(request.POST, instance=player_role, person=player_role.person, organization=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, _('¡Rol actualizado correctamente!'))
            return redirect('rosters:person_detail', person_id=player_role.person.id)
    else:
        form = PlayerRoleForm(instance=player_role, person=player_role.person, organization=request.tenant)
    
    context = {
        'form': form,
        'person': player_role.person,
        'player_role': player_role,
        'title': _('Editar Rol de Jugador - %(name)s') % {'name': player_role.person.full_name},
        'submit_text': _('Guardar Cambios'),
        'role_type': 'player',
    }
    
    return render(request, 'rosters/role_form.html', context)


@tenant_access_required(manager=True)
def staff_role_edit(request, role_id):
    """Vista para editar un rol de staff"""
    staff_role = get_tenant_object_or_404(
        StaffRole.objects.select_related('person', 'team'),
        request.tenant, user=request.user, id=role_id,
    )
    
    # Verificar permisos
    can_edit = request.user.can_edit_person(staff_role.person, request.tenant)
    if not can_edit:
        messages.error(request, _('No tienes permisos para editar este rol.'))
        return redirect('rosters:person_detail', person_id=staff_role.person.id)
    
    if request.method == 'POST':
        form = StaffRoleForm(request.POST, instance=staff_role, person=staff_role.person, organization=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, _('¡Rol actualizado correctamente!'))
            return redirect('rosters:person_detail', person_id=staff_role.person.id)
    else:
        form = StaffRoleForm(instance=staff_role, person=staff_role.person, organization=request.tenant)
    
    context = {
        'form': form,
        'person': staff_role.person,
        'staff_role': staff_role,
        'title': _('Editar Rol de Staff - %(name)s') % {'name': staff_role.person.full_name},
        'submit_text': _('Guardar Cambios'),
        'role_type': 'staff',
    }
    
    return render(request, 'rosters/role_form.html', context)


@tenant_access_required(manager=True)
@require_POST
def player_role_toggle_active(request, role_id):
    """Vista AJAX para activar/desactivar rol de jugador"""
    player_role = get_tenant_object_or_404(
        PlayerRole.objects, request.tenant, user=request.user, id=role_id,
    )
    
    # Verificar permisos
    can_edit = request.user.can_edit_person(player_role.person, request.tenant)
    if not can_edit:
        return JsonResponse({'success': False, 'error': _('Sin permisos')}, status=403)
    
    player_role.is_active = not player_role.is_active
    player_role.save()
    
    if player_role.is_active:
        messages.success(request, _('Rol de jugador activado correctamente.'))
    else:
        messages.success(request, _('Rol de jugador desactivado correctamente.'))
    
    return JsonResponse({'success': True, 'is_active': player_role.is_active})


@tenant_access_required(manager=True)
@require_POST
def staff_role_toggle_active(request, role_id):
    """Vista AJAX para activar/desactivar rol de staff"""
    staff_role = get_tenant_object_or_404(
        StaffRole.objects, request.tenant, user=request.user, id=role_id,
    )
    
    # Verificar permisos
    can_edit = request.user.can_edit_person(staff_role.person, request.tenant)
    if not can_edit:
        return JsonResponse({'success': False, 'error': _('Sin permisos')}, status=403)
    
    staff_role.is_active = not staff_role.is_active
    staff_role.save()
    
    if staff_role.is_active:
        messages.success(request, _('Rol de staff activado correctamente.'))
    else:
        messages.success(request, _('Rol de staff desactivado correctamente.'))
    
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
