import logging
import re

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from ilovevoley.competitions.services.acta_roster import (
    acta_roster_gaps,
    create_roster_players,
    person_candidates,
)
from ilovevoley.competitions.services.team_season_stats import get_team_season_summary
from ilovevoley.core.mixins import get_club_team_name_filter
from ilovevoley.core.models import Category, Season
from ilovevoley.core.season_utils import resolve_season_filter
from ilovevoley.core.tenancy import get_tenant_object_or_404
from ilovevoley.core.tenant_utils import tenant_access_required, user_is_tenant_manager
from ilovevoley.rosters.models import Person, PlayerRole, StaffRole
from ilovevoley.teams.identity import (
    one_team_per_identity,
    seasonal_appearance_name,
    stable_roster_label,
)
from ilovevoley.teams.models import Club, Team
from ilovevoley.videos.utils import normalize_team_name

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
    user_categories = request.user.preferred_categories_for(request.tenant)
    if not user_categories.exists():
        user_categories = Category.objects.filter(is_active=True)

    # Query base para equipos del club
    teams_query = Team.objects.select_related("category", "club").filter(is_active=True).filter(get_club_team_name_filter(request.tenant))
    
    # Filtrar por categorías preferidas del usuario
    category_filter = request.GET.get("category")
    show_all = request.GET.get("show_all", "0") == "1"
    
    if not show_all and not category_filter:
        teams_query = teams_query.filter(category__in=user_categories)
    elif category_filter:
        teams_query = teams_query.filter(category_id=category_filter)
    
    # Ordenar por categoría y nombre
    teams = one_team_per_identity(teams_query.order_by("category__name", "name"))

    # Temporada a mostrar (activa por defecto)
    season_filter, selected_season = resolve_season_filter(request)

    # Añadir contadores de plantilla usando nueva estructura Person-Role
    for team in teams:
        players = PlayerRole.objects.filter(identity_id=team.identity_id, is_active=True)
        staff = StaffRole.objects.filter(identity_id=team.identity_id, is_active=True)
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
        Team.objects.select_related(
            "category", "club", "identity__club", "identity__category",
        ),
        request.tenant, user=request.user, id=team_id,
    )
    
    # Temporada a mostrar (activa por defecto)
    season_filter, selected_season = resolve_season_filter(request)

    # Plantilla base: roles activos de la temporada seleccionada. Es la misma
    # regla que usan el listado de equipos y la vista general de plantillas, así
    # que los contadores coinciden entre superficies.
    # La plantilla es de la identidad, no de la fila (fase) federativa (#447).
    roster_players = PlayerRole.objects.filter(identity_id=team.identity_id, is_active=True)
    roster_staff = StaffRole.objects.filter(identity_id=team.identity_id, is_active=True)
    if season_filter:
        roster_players = roster_players.filter(season=season_filter)
        roster_staff = roster_staff.filter(season=season_filter)
    roster_players = roster_players.select_related('person')
    roster_staff = roster_staff.select_related('person')

    # Los filtros de posición/rol solo acotan las listas mostradas; las
    # estadísticas de cabecera siguen reflejando la plantilla completa.
    player_roles = roster_players.order_by("jersey_number", "person__last_name", "person__first_name")
    staff_roles = roster_staff.order_by("role", "person__last_name", "person__first_name")

    position_filter = request.GET.get("position")
    if position_filter:
        player_roles = player_roles.filter(position=position_filter)

    role_filter = request.GET.get("role")
    if role_filter:
        staff_roles = staff_roles.filter(role=role_filter)

    # Estadísticas de la plantilla usando nueva estructura
    stats = {
        "total_players": roster_players.count(),
        "total_staff": roster_staff.count(),
        "players_with_jersey": 0,
        "positions_covered": 0,
        "positions_distribution": {},
        "roles_distribution": {},
    }

    # Contar jugadores con dorsal asignado
    stats["players_with_jersey"] = roster_players.filter(jersey_number__isnull=False).count()

    # Posiciones cubiertas y distribución por posiciones (plantilla completa)
    positions_with_players = set()
    for player_role in roster_players:
        if player_role.position:
            positions_with_players.add(player_role.position)
        pos = player_role.get_position_display() if player_role.position else "Sin asignar"
        stats["positions_distribution"][pos] = stats["positions_distribution"].get(pos, 0) + 1
    stats["positions_covered"] = len(positions_with_players)

    # Distribución por roles del staff (plantilla completa)
    for staff_role in roster_staff:
        role = staff_role.get_role_display()
        stats["roles_distribution"][role] = stats["roles_distribution"].get(role, 0) + 1
    
    # Opciones para filtros - usar las opciones de los nuevos modelos
    position_choices = PlayerRole.POSITION_CHOICES
    role_choices = StaffRole.STAFF_ROLES

    # Título estable (club + categoría) y nombre federativo de la temporada (#512).
    if team.identity_id:
        roster_title = stable_roster_label(team.identity)
        appearance = seasonal_appearance_name(team.identity, season_filter)
        roster_season_name = (
            appearance
            if appearance
            and normalize_team_name(appearance) != normalize_team_name(roster_title)
            else None
        )
    else:
        roster_title = team.name
        roster_season_name = None

    # Resumen de clasificación: temporada del filtro, o la activa si el selector
    # apunta a ella (selected_season). Con «todas» no hay agregación.
    summary_season = season_filter
    if summary_season is None and selected_season:
        summary_season = Season.objects.filter(pk=selected_season).first()
    team_season_summary = get_team_season_summary(
        team.identity, summary_season, request.tenant,
    )

    can_manage = user_is_tenant_manager(request.user, request.tenant)

    # Dorsales que aparecen en las actas de la temporada y aún no tienen ficha
    # (#569). Solo se calculan para quien puede dar de alta jugadores.
    acta_gaps, acta_gap_season = [], None
    if can_manage and team.identity_id:
        acta_gap_season = season_filter or Season.objects.current()
        if acta_gap_season is not None:
            acta_gaps = acta_roster_gaps(team.identity, acta_gap_season)
            # La lista del club se carga una sola vez, y solo si hay huecos que
            # resolver: es el caso raro, no la visita habitual a la plantilla.
            if acta_gaps:
                in_club = list(Person.objects.for_tenant(request.tenant))
                for gap in acta_gaps:
                    gap["candidates"] = person_candidates(
                        gap["name_acta"], request.tenant, in_club=in_club,
                    )

    context = {
        "team": team,
        "roster_title": roster_title,
        "roster_season_name": roster_season_name,
        "player_roles": player_roles,
        "staff_roles": staff_roles,
        "stats": stats,
        "position_choices": position_choices,
        "role_choices": role_choices,
        "seasons": Season.objects.all(),
        "can_manage": can_manage,
        "selected_season": selected_season,
        "season_filtered": "season" in request.GET,
        "selected_position": position_filter,
        "selected_role": role_filter,
        "team_season_summary": team_season_summary,
        "acta_gaps": acta_gaps,
        "acta_gap_season": acta_gap_season,
        "person_last_name_max_length": Person._meta.get_field("last_name").max_length,
    }
    
    return render(request, "teams/team_roster.html", context)


@tenant_access_required(manager=True)
@require_POST
def roster_from_acta(request, team_id):
    """Convierte dorsales del acta en fichas provisionales de la plantilla (#569).

    La confirmación llega del formulario de la plantilla: cada fila trae su
    dorsal, el apellido leído (editable) y, si el manager lo elige, una ficha
    existente que se reutiliza en vez de crear una nueva.
    """
    team = get_tenant_object_or_404(
        Team.objects, request.tenant, user=request.user, id=team_id,
    )
    if not team.identity_id:
        messages.error(request, _(
            "Este equipo no tiene identidad asignada; asígnala en el admin antes de dar de alta la plantilla."
        ))
        return redirect("teams:team_roster", team.id)

    raw_season = request.POST.get("season", "")
    season = Season.objects.filter(pk=raw_season).first() if raw_season.isdecimal() else None
    season = season or Season.objects.current()
    if season is None:
        messages.error(request, _("No hay temporada activa; elige una antes de crear las fichas."))
        return redirect("teams:team_roster", team.id)

    selections = []
    for key, value in request.POST.items():
        if not key.startswith("create_") or value != "1":
            continue
        jersey = key[len("create_"):]
        if not jersey.isdecimal():
            continue
        person_id = request.POST.get(f"person_{jersey}", "")
        selections.append({
            "jersey": int(jersey),
            "last_name": request.POST.get(f"last_name_{jersey}", ""),
            "person_id": int(person_id) if person_id.isdecimal() else None,
        })

    result = create_roster_players(team.identity, season, request.tenant, selections)
    if not selections:
        messages.info(request, _("No has seleccionado ningún dorsal."))
    if result["created"] or result["reused"]:
        messages.success(request, _(
            "%(created)s fichas creadas y %(reused)s reutilizadas."
        ) % result)
    for error in result["errors"]:
        messages.error(request, error)

    roster_url = reverse("teams:team_roster", args=[team.id])
    return redirect(f"{roster_url}?season={season.pk}")


__all__ = [
    'ajax_register_team',
    'roster_from_acta',
    'team_list',
    'team_roster',
]
