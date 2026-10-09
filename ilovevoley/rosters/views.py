import logging
from io import BytesIO

from PIL import Image as PILImage
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Prefetch, Q
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from ilovevoley.core.image_utils import InvalidImageError, decode_cropped_image
from ilovevoley.core.models import Category, Season
from ilovevoley.core.season_utils import resolve_season_filter
from ilovevoley.core.tenancy import get_tenant_object_or_404
from ilovevoley.core.tenant_utils import person_belongs_to_tenant, tenant_access_required, user_is_tenant_manager
from ilovevoley.competitions.models import MatchLineup
from ilovevoley.content.models import Image
from ilovevoley.competitions.services.lineups import get_player_season_stats, get_rival_seasons, get_season_rivals
from ilovevoley.teams.identity import one_team_per_identity
from ilovevoley.teams.models import Team
from ilovevoley.competitions.result_card import _file_field_bytes
from .forms import BulkPlayerRosterForm, PersonForm, PlayerRoleForm, StaffRoleForm
from .models import Person, PlayerRole, StaffRole
from .player_card import card_highlight, card_photo_allowed, render_player_card

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
        Prefetch("identity__player_roles", queryset=PlayerRole.objects.filter(**role_filter).select_related("person")),
        Prefetch("identity__staff_roles", queryset=StaffRole.objects.filter(**role_filter).select_related("person")),
    ).filter(is_active=True).for_tenant(request.tenant)
    
    # Filtrar por categorías preferidas del usuario
    category_filter = request.GET.get("category")
    show_all = request.GET.get("show_all", "0") == "1"
    
    if not show_all and not category_filter:
        teams_query = teams_query.filter(category__in=user_categories)
    elif category_filter:
        teams_query = teams_query.filter(category_id=category_filter)
    
    teams = one_team_per_identity(teams_query.order_by("category__name", "name"))

    # Estadísticas generales
    total_stats = {
        "total_teams": len(teams),
        "total_players": 0,
        "total_staff": 0,
        "teams_with_good_roster": 0,  # Equipos con 8+ jugadores (buen número para rotaciones)
        "categories_summary": {},
    }
    
    for team in teams:
        active_player_roles = team.identity.player_roles.all() if team.identity_id else []
        active_staff_roles = team.identity.staff_roles.all() if team.identity_id else []
        
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
        "can_manage": user_is_tenant_manager(request.user, request.tenant),
    }
    
    return render(request, "rosters/roster_overview.html", context)


@tenant_access_required()
def person_list(request):
    """Vista de listado de personas del club"""
    # Solo fichas del club del tenant activo
    people = Person.objects.for_tenant(request.tenant).filter(
        is_active=True,
    ).prefetch_related(
        'player_roles__identity__category',
        'staff_roles__identity__category'
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
    for person in page_obj:
        person.active_player_roles = person.get_player_roles().for_tenant(request.tenant)
        person.active_staff_roles = person.get_staff_roles().for_tenant(request.tenant)
    
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
    el usuario solo ve sus propios datos (nunca recibe un id por URL). Los
    padres ven además la lista de sus hijos (#457).
    """
    person = Person.objects.filter(user=request.user).first()
    children = [
        {'person': child, 'has_card': _card_role(child, request.tenant) is not None}
        for child in request.user.children.order_by('first_name')
    ]
    if person is None and not children:
        raise Http404
    context = _trajectory_context(request, person) if person else {'person': None}
    return render(request, 'rosters/my_profile.html', {**context, 'children': children})


@tenant_access_required()
def child_profile(request, person_id):
    """«Tú» de un hijo: su trayectoria en todos los clubes, como la del propio usuario.

    Universal igual que «Tú»: si el hijo cambia de club, sus padres siguen viendo
    las temporadas anteriores. Solo se resuelve entre los hijos del usuario, así
    que un id ajeno da 404 sin importar el tenant.
    """
    person = get_object_or_404(request.user.children.all(), pk=person_id)
    return render(request, 'rosters/my_profile.html', {**_trajectory_context(request, person), 'is_child': True})


def _trajectory_context(request, person):
    by_season = {}
    for kind, model in (('player_roles', PlayerRole), ('staff_roles', StaffRole)):
        roles = model.objects.filter(person=person).select_related('identity__category', 'identity__club', 'season')
        for role in roles.order_by('identity__core_name'):
            by_season.setdefault(role.season, {'season': role.season, 'player_roles': [], 'staff_roles': []})[kind].append(role)
    tagged_images_qs = Image.objects.for_tenant(request.tenant).filter(
        persons=person, status='approved'
    ).order_by('-upload_date')
    rival_seasons = get_rival_seasons(person)
    # Los rivales nunca cruzan temporadas: «todas» (?season=) cae en la más reciente.
    rival_season = _resolve_person_stat_season(request, rival_seasons) or rival_seasons.first()
    # La ficha del club se abre con el mismo filtro que person_detail, para no enlazar a un 404.
    visible = Person.objects.all() if request.user.is_superuser else Person.objects.for_tenant(request.tenant)
    return {
        'person': person,
        'seasons': sorted(by_season.values(), key=lambda s: s['season'].start_year, reverse=True),
        'rival_seasons': rival_seasons,
        'rival_season': rival_season,
        'rivals': get_season_rivals(person, rival_season) if rival_season else [],
        'in_current_tenant': visible.filter(pk=person.pk).exists(),
        'has_card': _card_role(person, request.tenant) is not None,
        'tagged_images': list(tagged_images_qs[:8]),
        'tagged_images_count': tagged_images_qs.count(),
    }


def _card_role(person, tenant):
    """Último rol de jugador en un equipo del club: el cromo es de esa temporada.

    Solo equipos del tenant, así que nunca sale el cromo de un rival.
    """
    return (
        person.player_roles.for_tenant(tenant).select_related('identity', 'season')
        .order_by('-season__start_year', '-is_active').first()
    )


def _card_person(request, person_id):
    """Ficha y rol del cromo, o 403/404.

    Lo generan el propio jugador, su familia y los gestores del club: es la
    imagen de un menor pensada para redes.
    """
    person = get_tenant_object_or_404(Person.objects.all(), request.tenant, user=request.user, id=person_id)
    if not request.user.is_authenticated or not request.user.can_edit_person(person, request.tenant):
        raise PermissionDenied
    role = _card_role(person, request.tenant)
    if role is None:
        raise Http404
    return person, role


def _card_photos(person, tenant):
    return Image.objects.for_tenant(tenant).filter(persons=person, status='approved').order_by('-upload_date')


@tenant_access_required()
def person_card_page(request, person_id):
    """Página del cromo (#457): vista previa, elección de foto, compartir y descargar."""
    person, role = _card_person(request, person_id)
    photo_allowed = card_photo_allowed(request.user, person)
    photos = list(_card_photos(person, request.tenant)[:24]) if photo_allowed else []
    default_photo = str(photos[0].id) if photos else ('perfil' if photo_allowed and person.photo else '0')
    return render(request, 'rosters/person_card.html', {
        'person': person,
        'role': role,
        'photo_allowed': photo_allowed,
        'photos': photos,
        'default_photo': default_photo,
    })


@tenant_access_required()
def person_card(request, person_id):
    """Cromo del jugador en PNG Story (o WebP reducido con ``?preview=1``).

    ``?foto=`` elige la imagen: el id de una foto etiquetada, ``perfil`` o ``0``
    (sin foto). Sin parámetro, la etiquetada más reciente o la de perfil.
    """
    person, role = _card_person(request, person_id)
    teams = Team.objects.for_tenant(request.tenant).filter(identity=role.identity)
    has_actas = MatchLineup.objects.filter(
        person=person, team__in=teams, match__league__season=role.season,
    ).exclude(match__status='withdrawn').exists()

    choice = request.GET.get('foto', '')
    photos = _card_photos(person, request.tenant)
    if choice == '0' or not card_photo_allowed(request.user, person):
        photo = None
    elif choice == 'perfil':
        photo = _file_field_bytes(person.photo)
    elif choice.isdecimal():
        tagged = photos.filter(id=choice).first()
        if tagged is None:
            raise Http404
        photo = _file_field_bytes(tagged.thumbnail_large or tagged.image)
    else:
        tagged = photos.first()
        photo = (tagged and _file_field_bytes(tagged.thumbnail_large or tagged.image)) or _file_field_bytes(person.photo)

    png = render_player_card(
        organization=request.tenant,
        person=person,
        role=role,
        highlight=card_highlight(person, teams, role.season) if has_actas else None,
        stats=get_player_season_stats(person, role.season, teams) if has_actas else None,
        photo=photo,
    )
    if request.GET.get('preview') == '1':
        preview = PILImage.open(BytesIO(png))
        preview.thumbnail((540, 960))
        buffer = BytesIO()
        preview.save(buffer, 'WEBP', quality=85)
        response = HttpResponse(buffer.getvalue(), content_type='image/webp')
        response['Cache-Control'] = 'no-store'
        return response
    response = HttpResponse(png, content_type='image/png')
    response['Content-Disposition'] = f'attachment; filename="cromo-{person.id}.png"'
    return response


@tenant_access_required()
def person_detail(request, person_id):
    """Vista de detalle de una persona"""
    person = get_tenant_object_or_404(
        Person.objects.select_related('user').prefetch_related(
            'player_roles__identity__category',
            'staff_roles__identity__category'
        ),
        request.tenant, user=request.user, id=person_id,
    )
    
    # Roles visibles solo en equipos del club del tenant
    tenant_teams = Team.objects.for_tenant(request.tenant)
    player_roles = person.player_roles.for_tenant(request.tenant).select_related('identity__category').order_by('-is_active', 'identity__core_name')
    staff_roles = person.staff_roles.for_tenant(request.tenant).select_related('identity__category').order_by('-is_active', 'identity__core_name')

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

    tagged_images_qs = Image.objects.for_tenant(request.tenant).filter(
        persons=person, status='approved'
    ).order_by('-upload_date')

    context = {
        'person': person,
        'player_roles': player_roles,
        'staff_roles': staff_roles,
        'can_edit': can_edit,
        'has_card': can_edit and _card_role(person, request.tenant) is not None,
        'seasons': seasons,
        'stat_season': stat_season,
        'player_stats': player_stats,
        'tagged_images': list(tagged_images_qs[:8]),
        'tagged_images_count': tagged_images_qs.count(),
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
        form = PersonForm(request.POST, request.FILES)
        
        if form.is_valid():
            person = form.save(commit=False)
            
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
            person.organizations.add(request.tenant)
            messages.success(request, _('¡Persona creada exitosamente! Ahora puedes agregar roles de jugador o staff.'))
            return redirect('rosters:person_detail', person_id=person.id)
    else:
        form = PersonForm()
    
    context = {
        'form': form,
        'existing_person': form.existing_person() if form.is_bound and hasattr(form, 'cleaned_data') else None,
        'title': _('Agregar Nueva Persona'),
        'submit_text': _('Crear Persona'),
    }
    
    return render(request, 'rosters/person_form.html', context)


@tenant_access_required(manager=True)
@require_POST
def person_quick_create(request):
    """Alta rápida de persona (nombre, apellidos, año) para el modal del alta masiva (#446).

    No vincula la ficha al usuario (``person_create`` lo hace con la primera que
    crea): aquí se dan de alta jugadores ajenos. Si la identidad ya existe en la
    plataforma responde 409 con la ficha; con ``adopt=1`` se vincula al club.
    """
    form = PersonForm(request.POST)
    if request.POST.get('adopt') == '1':
        form.is_valid()
        person = form.existing_person()
        if person is None:
            raise Http404
    elif form.is_valid():
        with transaction.atomic():
            person = form.save()
            person.organizations.add(request.tenant)
        return JsonResponse({'id': person.pk, 'name': person.full_name, 'birth_year': person.birth_year})
    else:
        existing = form.existing_person()
        if existing:
            return JsonResponse({'existing': {
                'name': existing.full_name, 'birth_year': existing.birth_year,
            }}, status=409)
        return JsonResponse({'errors': {k: [str(m) for m in v] for k, v in form.errors.items()}}, status=400)
    person.organizations.add(request.tenant)
    return JsonResponse({'id': person.pk, 'name': person.full_name, 'birth_year': person.birth_year})


@tenant_access_required(manager=True)
@require_POST
def person_adopt(request):
    """Vincula al club una ficha global existente, identificada por nombre y año.

    Exigir la identidad completa evita adoptar fichas por id: el gestor solo
    puede vincular una persona cuyos datos ya conoce.
    """
    year = request.POST.get('birth_year', '')
    if not (year.isascii() and year.isdigit()):
        raise Http404
    person = Person._base_manager.filter(
        first_name=request.POST.get('first_name', ''),
        last_name=request.POST.get('last_name', ''),
        birth_year=int(year),
    ).first()
    if person is None:
        raise Http404
    person.organizations.add(request.tenant)
    messages.success(request, _('Persona añadida a tu club. Ahora puedes agregar roles de jugador o staff.'))
    return redirect('rosters:person_detail', person_id=person.id)


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
            request.POST, request.FILES, instance=person,
        )
        
        if form.is_valid():
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
            messages.success(request, _('¡Rol de jugador agregado en %(team)s!') % {'team': player_role.identity})
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


def _previous_season_initial(team, season):
    """Filas precargadas con la plantilla de la temporada anterior del mismo equipo (identidad)."""
    previous = Season.objects.filter(start_year__lt=season.start_year).order_by('-start_year').first()
    if previous is None:
        return {}, None
    roles = PlayerRole.objects.filter(identity_id=team.identity_id, season=previous, is_active=True)
    return {role.person_id: (role.jersey_number, role.position) for role in roles}, previous


@tenant_access_required(manager=True)
def player_roster_bulk_add(request, team_id):
    """Alta masiva de jugadores en un equipo y temporada (#446)."""
    team = get_tenant_object_or_404(Team.objects, request.tenant, user=request.user, id=team_id)
    if not team.identity_id:
        # La plantilla cuelga de la identidad (#447); sin ella no hay dónde guardarla.
        messages.error(request, _('Este equipo no tiene identidad asignada; asígnala en el admin antes de dar de alta la plantilla.'))
        return redirect('teams:team_roster', team.id)
    seasons = Season.objects.all()
    raw_season = request.POST.get('season') or request.GET.get('season')
    season = seasons.filter(pk=raw_season).first() if raw_season and raw_season.isdigit() else None
    season = season or Season.objects.current()

    candidates = Person.objects.for_tenant(request.tenant).filter(is_active=True).exclude(
        pk__in=PlayerRole.objects.filter(identity_id=team.identity_id, season=season, is_active=True).values('person_id'),
    ).order_by('last_name', 'first_name')

    previous = None
    if request.method == 'POST':
        form = BulkPlayerRosterForm(team, season, candidates, data=request.POST)
        if form.is_valid():
            try:
                created = form.save()
            except IntegrityError:
                # Carrera con otro alta: el constraint de BD no debe ser un 500.
                form.errors.append(_('Algún dorsal o jugador acaba de ser asignado. Revisa los datos.'))
            else:
                messages.success(request, _('%(n)s jugadores añadidos a %(team)s.') % {'n': created, 'team': team})
                return redirect(f"{reverse('teams:team_roster', args=[team.id])}?season={season.pk}")
    else:
        initial = {}
        if request.GET.get('copy') == '1':
            initial, previous = _previous_season_initial(team, season)
            if not initial:
                messages.info(request, _('No hay plantilla en la temporada anterior para copiar.'))
        form = BulkPlayerRosterForm(team, season, candidates, initial=initial)

    return render(request, 'rosters/roster_bulk_add.html', {
        'form': form, 'team': team, 'season': season, 'seasons': seasons, 'previous_season': previous,
    })


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
            messages.success(request, _('¡Rol de staff agregado en %(team)s!') % {'team': staff_role.identity})
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
        PlayerRole.objects.select_related('person', 'identity'),
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
        StaffRole.objects.select_related('person', 'identity'),
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
