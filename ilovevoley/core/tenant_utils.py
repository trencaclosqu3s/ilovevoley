from functools import wraps

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

ORG_CACHE_TTL = 300
ORG_CACHE_PREFIX = 'tenant_org:'


def hex_to_rgb_channels(hex_color, default='155 127 191'):
    """Convierte un color hex (#RGB o #RRGGBB) a canales RGB separados ("r g b").

    Tailwind define la marca como ``rgb(var(--brand-rgb) / <alpha-value>)``. Sin
    los canales por separado las utilidades ``bg-opacity-*`` no tienen efecto y
    el color de marca se pinta sólido, dejando ilegible el texto que usa la
    misma marca.
    """
    if not hex_color:
        return default
    value = hex_color.strip().lstrip('#')
    if len(value) == 3:
        value = ''.join(ch * 2 for ch in value)
    if len(value) != 6:
        return default
    try:
        red, green, blue = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return default
    return f'{red} {green} {blue}'


def _org_cache_key(slug):
    return f'{ORG_CACHE_PREFIX}{slug}'


def invalidate_organization_cache(slug):
    if slug:
        cache.delete(_org_cache_key(slug))


def get_organization_by_slug(slug):
    from ilovevoley.core.models import Organization

    key = _org_cache_key(slug)
    org_id = cache.get(key)
    if org_id is not None:
        if org_id == 0:
            return None
        try:
            return Organization.objects.get(pk=org_id, is_active=True)
        except Organization.DoesNotExist:
            cache.delete(key)

    try:
        org = Organization.objects.get(slug=slug, is_active=True)
        cache.set(key, org.pk, ORG_CACHE_TTL)
        return org
    except Organization.DoesNotExist:
        cache.set(key, 0, ORG_CACHE_TTL)
        return None


def get_tenant_base_domain(request=None):
    configured = getattr(settings, 'TENANT_BASE_DOMAIN', None)
    if configured:
        return configured
    if request is not None:
        host = request.get_host().split(':')[0]
        parts = host.split('.')
        if len(parts) >= 2:
            return '.'.join(parts[-2:])
        return request.get_host()
    return 'localhost:8000'


def build_tenant_url(slug, request=None):
    protocol = 'https' if not settings.DEBUG else 'http'
    base_domain = get_tenant_base_domain(request)
    return f'{protocol}://{slug}.{base_domain}/'


def build_absolute_url(path, tenant=None, request=None):
    """
    Construye una URL absoluta considerando el tenant (subdominio) o el dominio base.
    """
    protocol = 'https' if not settings.DEBUG else 'http'
    if tenant and getattr(tenant, 'slug', None):
        base = build_tenant_url(tenant.slug, request)
        return f"{base.rstrip('/')}/{path.lstrip('/')}"
    base_domain = get_tenant_base_domain(request)
    return f"{protocol}://{base_domain}/{path.lstrip('/')}"



def user_has_approved_membership(user, tenant):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if not tenant:
        return False
    from ilovevoley.users.models import Membership

    return Membership.objects.filter(
        user=user,
        organization=tenant,
        is_approved=True,
    ).exists()


def user_is_tenant_manager(user, tenant):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if not tenant:
        return False
    from ilovevoley.users.models import Membership

    return Membership.objects.filter(
        user=user,
        organization=tenant,
        is_approved=True,
        role__in=['manager', 'admin'],
    ).exists()


def user_is_tenant_staff(user, tenant):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if not tenant:
        return False
    from ilovevoley.users.models import Membership

    return Membership.objects.filter(
        user=user,
        organization=tenant,
        is_approved=True,
        role='admin',
    ).exists()


def can_moderate_images(user, tenant=None):
    """Determina si un usuario tiene permisos para moderar imágenes en un tenant o globalmente."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if not tenant:
        return False
    return user_is_tenant_manager(user, tenant) or user_is_tenant_staff(user, tenant)


def approve_user_membership(user, tenant=None):
    """Aprueba al usuario globalmente y su membresía en el tenant indicado (o todas las pendientes)."""
    from ilovevoley.users.models import Membership

    user.is_approved = True
    user.is_active = True
    user.save(update_fields=['is_approved', 'is_active'])

    qs = Membership.objects.filter(user=user, is_approved=False)
    if tenant is not None:
        qs = qs.filter(organization=tenant)
    qs.update(is_approved=True)


def reject_user_membership(user, tenant):
    """Deniega la solicitud de membresía del usuario en el tenant.

    No toca la cuenta global (is_active/is_approved): el usuario puede seguir
    perteneciendo a otras organizaciones.
    """
    from ilovevoley.users.models import Membership

    return Membership.objects.filter(
        user=user, organization=tenant, is_approved=False
    ).delete()


def tenant_access_required(*, manager=False, staff=False, api=False):
    """Requiere tenant, login y membresía aprobada (u opciones manager/staff).

    Con ``api=True`` el acceso denegado responde 403 en lugar de redirigir, y
    los superusuarios pasan aunque no haya tenant resuelto (p. ej. peticiones
    internas de medios servidas por nginx con X-Accel-Redirect).
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if api and request.user.is_authenticated and request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            if not request.user.is_authenticated:
                if api:
                    raise PermissionDenied
                return redirect_to_login(request.get_full_path())
            tenant = getattr(request, 'tenant', None)
            if not tenant:
                if api:
                    raise PermissionDenied
                return redirect('landing')
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            if staff:
                if not (user_is_tenant_staff(request.user, tenant) or user_is_tenant_manager(request.user, tenant)):
                    raise PermissionDenied
            elif manager:
                if not user_is_tenant_manager(request.user, tenant):
                    raise PermissionDenied
            elif not user_has_approved_membership(request.user, tenant):
                if api:
                    raise PermissionDenied
                return redirect('/pending-approval/')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def team_belongs_to_tenant(team, tenant):
    """Comprueba si un equipo pertenece al club u organización del tenant mediante FK explícita."""
    if not team or not tenant:
        return False
    from ilovevoley.core.mixins import get_tenant_club
    club = get_tenant_club(tenant)
    if club is None or team.club_id is None:
        return False
    return team.club_id == club.id


def person_belongs_to_tenant(person, tenant):
    """Comprueba si una persona pertenece a un tenant o puede ser gestionada por él.

    Una persona pertenece al tenant si:
    1. Su organization FK coincide con el tenant.
    2. Tiene roles (jugador o staff) en equipos pertenecientes al tenant.
    3. Su usuario vinculado tiene membresía aprobada en el tenant.
    4. Está vinculada como hijo/a de un usuario con membresía aprobada en el tenant.

    Si no cumple ninguna de estas condiciones verificables, retorna False para evitar IDOR
    cross-tenant sobre fichas huérfanas sin roles.
    """
    if not person or not tenant:
        return False

    if getattr(person, 'organization_id', None) is not None:
        return person.organization_id == tenant.id

    player_roles = list(person.player_roles.select_related('team').all())
    staff_roles = list(person.staff_roles.select_related('team').all())
    all_roles = player_roles + staff_roles

    if all_roles:
        return any(team_belongs_to_tenant(role.team, tenant) for role in all_roles)

    from ilovevoley.users.models import Membership

    if person.user_id:
        return Membership.objects.filter(
            user_id=person.user_id,
            organization=tenant,
            is_approved=True,
        ).exists()

    if Membership.objects.filter(
        user__children=person,
        organization=tenant,
        is_approved=True,
    ).exists():
        return True

    return False

