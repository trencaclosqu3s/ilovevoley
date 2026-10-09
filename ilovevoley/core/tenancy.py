"""Aislamiento multi-tenant centralizado en el ORM.

Cada modelo con ámbito de club expone ``.for_tenant(tenant)`` en su queryset y
las vistas resuelven objetos con :func:`get_tenant_object_or_404`, de modo que
el filtrado por organización no se repite como
``if obj.organization != tenant: raise Http404`` por cada vista.

Hay dos formas de pertenencia:

* FK directa ``organization`` (``Video``, ``Image``): filtro exacto.
* Modelos globales acotados por el club del tenant (``Match``, ``League``,
  ``Team``): reutilizan los filtros híbridos de ``core.mixins``.
"""

from django.db import models
from django.shortcuts import get_object_or_404


class TenantQuerySet(models.QuerySet):
    """Base de querysets con ámbito de tenant.

    Las subclases implementan :meth:`tenant_filter` devolviendo el ``Q`` que
    restringe el queryset a la organización indicada.
    """

    def for_tenant(self, tenant):
        """Restringe el queryset a los objetos accesibles por ``tenant``.

        Sin tenant (dominio raíz) no hay ámbito válido y devuelve un queryset
        vacío en lugar de exponer datos globales.
        """
        if tenant is None:
            return self.none()
        return self.filter(self.tenant_filter(tenant))

    def tenant_filter(self, tenant):
        raise NotImplementedError


class OrganizationTenantQuerySet(TenantQuerySet):
    """Modelos con FK directa ``organization`` (``Video``, ``Image``)."""

    def tenant_filter(self, tenant):
        return models.Q(organization=tenant)


class PersonTenantQuerySet(TenantQuerySet):
    """Fichas globales: visibles en el club vinculado o donde tengan roles."""

    def tenant_filter(self, tenant):
        from ilovevoley.teams.models import Team

        club_identities = Team.objects.for_tenant(tenant).values('identity')
        return (
            models.Q(organizations=tenant)
            | models.Q(player_roles__identity__in=club_identities)
            | models.Q(staff_roles__identity__in=club_identities)
        )

    def for_tenant(self, tenant):
        # Los joins de roles duplican filas: se acota por pk para devolver un
        # queryset sin distinct() (sigue admitiendo order_by, update, etc.).
        if tenant is None:
            return self.none()
        return self.filter(pk__in=self.model._base_manager.filter(self.tenant_filter(tenant)).values('pk'))

    def active_for_tenant(self, tenant):
        """Fichas para navegación del tenant (#478): alta activa en el club o
        rol activo en un equipo del club en la temporada actual.

        Más estrecho que ``for_tenant`` (que mantiene el acceso histórico por
        URL a fichas dadas de baja): los listados y selectores no deben
        ofrecer fichas con baja deportiva. La baja gana: una ficha dada de
        baja aquí no sale aunque conserve un rol activo de la temporada
        (dar de baja debe limpiar también las plantillas vigentes). Sin
        temporada activa configurada solo cuenta la pertenencia.
        """
        if tenant is None:
            return self.none()
        from ilovevoley.core.models import Season
        from ilovevoley.teams.models import Team

        qs = self.model._base_manager.filter(
            models.Q(
                club_memberships__organization=tenant,
                club_memberships__is_active=True,
            )
        )
        season = Season.objects.current()
        if season is not None:
            club_identities = Team.objects.for_tenant(tenant).values('identity')
            qs = qs | self.model._base_manager.filter(
                models.Q(
                    player_roles__identity__in=club_identities,
                    player_roles__is_active=True,
                    player_roles__season=season,
                )
                | models.Q(
                    staff_roles__identity__in=club_identities,
                    staff_roles__is_active=True,
                    staff_roles__season=season,
                )
            )
        # La baja del club precede a cualquier rol activo de la temporada.
        given_leave = self.model._base_manager.filter(
            models.Q(
                club_memberships__organization=tenant,
                club_memberships__is_active=False,
            )
        )
        return self.filter(pk__in=qs.values('pk')).exclude(pk__in=given_leave.values('pk'))


class PersonRoleTenantQuerySet(TenantQuerySet):
    """Roles de una persona: pertenecen al club de los equipos de su identidad.

    Se pasa por ``Team.for_tenant`` (y no por ``identity.club``) para conservar
    los equipos que entran en el tenant por nombre y no por FK (#447).
    """

    def tenant_filter(self, tenant):
        from ilovevoley.teams.models import Team

        return models.Q(identity__in=Team.objects.for_tenant(tenant).values('identity'))


class MatchTenantQuerySet(TenantQuerySet):
    """Partidos: pertenecen al tenant si juega un equipo de su club."""

    def tenant_filter(self, tenant):
        from ilovevoley.core.mixins import get_club_team_filter

        return get_club_team_filter(tenant)


class TeamTenantQuerySet(TenantQuerySet):
    """Equipos: pertenecen al tenant si son del club (FK) o casan por nombre."""

    def tenant_filter(self, tenant):
        from ilovevoley.core.mixins import get_club_team_name_filter

        return get_club_team_name_filter(tenant)


def get_tenant_object_or_404(queryset, tenant, *, user=None, **kwargs):
    """``get_object_or_404`` acotado al tenant.

    Un superusuario global queda exento del filtro (moderación), igual que en
    el resto de la app. Para el resto, un objeto de otra organización devuelve
    404 (no 403) para no revelar su existencia.

    ``queryset`` admite un queryset ya construido o una clase de modelo (se usa
    su manager por defecto).
    """
    if isinstance(queryset, type) and issubclass(queryset, models.Model):
        queryset = queryset._default_manager
    if getattr(user, 'is_superuser', False):
        return get_object_or_404(queryset, **kwargs)
    return get_object_or_404(queryset.for_tenant(tenant), **kwargs)
