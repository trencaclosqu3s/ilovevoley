from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q

from .tenant_utils import user_has_approved_membership, user_is_tenant_manager


def get_club_team_names(tenant):
    """Extrae los nombres de equipos del club desde la organización o fallback."""
    if tenant and tenant.club_team_names:
        return list(tenant.club_team_names.values())
    else:
        fallback = getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')
        return [fallback]


def get_primary_club_team_name(tenant):
    """Nombre principal del club para filtros por icontains en plantillas."""
    names = get_club_team_names(tenant)
    return names[0] if names else getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')


def get_tenant_club(tenant):
    """Club federativo vinculado al tenant, si lo tiene."""
    return getattr(tenant, 'club', None) if tenant else None


def get_club_team_filter(tenant):
    """Retorna un Q que filtra partidos por los equipos del tenant.

    Usa la FK ``Team.club`` cuando el tenant tiene club vinculado y mantiene el
    matching por nombre (``club_team_names``) como fallback para equipos que aún
    no tienen ``club`` asignado (datos históricos). Un equipo con otro club
    nunca entra por nombre: eso aislaría datos de otros tenants.
    """
    q = Q()
    club = get_tenant_club(tenant)
    only_orphans = club is not None

    for name in get_club_team_names(tenant):
        if only_orphans:
            q |= (
                Q(home_team__name__icontains=name, home_team__club__isnull=True) |
                Q(away_team__name__icontains=name, away_team__club__isnull=True) |
                Q(home_team__isnull=True, home_team_text__icontains=name) |
                Q(away_team__isnull=True, away_team_text__icontains=name)
            )
        else:
            q |= (
                Q(home_team__name__icontains=name) |
                Q(away_team__name__icontains=name) |
                Q(home_team_text__icontains=name) |
                Q(away_team_text__icontains=name)
            )

    if only_orphans:
        q |= Q(home_team__club=club) | Q(away_team__club=club)
    return q


def get_club_team_name_filter(tenant):
    """Retorna un Q que filtra equipos (Team) del club del tenant.

    Incluye todos los equipos con la FK al club vinculado y, además, los que
    casan por nombre con ``club_team_names`` cuando todavía no tienen club.
    """
    q = Q()
    club = get_tenant_club(tenant)

    if club is not None:
        q |= Q(club=club)
        for name in get_club_team_names(tenant):
            q |= Q(name__icontains=name, club__isnull=True)
    else:
        for name in get_club_team_names(tenant):
            q |= Q(name__icontains=name)
    return q


class TenantMemberRequired(LoginRequiredMixin):
    """
    Requiere Membership aprobada en request.tenant.
    Subclases pueden definir required_roles para exigir un rol concreto.
    """
    required_roles = None  # None = cualquier member aprobado

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            raise PermissionDenied
        if not user_has_approved_membership(request.user, tenant):
            raise PermissionDenied
        if self.required_roles:
            from videosvoley.users.models import Membership
            if not Membership.objects.filter(
                user=request.user,
                organization=tenant,
                is_approved=True,
                role__in=self.required_roles,
            ).exists():
                raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class TenantManagerRequired(TenantMemberRequired):
    """Requiere role manager o admin en el tenant."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.is_superuser:
            return super(TenantMemberRequired, self).dispatch(request, *args, **kwargs)
        tenant = getattr(request, 'tenant', None)
        if not tenant or not user_is_tenant_manager(request.user, tenant):
            raise PermissionDenied
        if not user_has_approved_membership(request.user, tenant):
            raise PermissionDenied
        return super(TenantMemberRequired, self).dispatch(request, *args, **kwargs)


class TenantAdminRequired(TenantMemberRequired):
    """Requiere role admin en el tenant."""
    required_roles = ['admin']
