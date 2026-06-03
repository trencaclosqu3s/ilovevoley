from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q


def get_club_team_filter(tenant):
    """Retorna un Q que filtra partidos por los equipos del tenant."""
    if tenant and tenant.club_team_names:
        team_names = list(tenant.club_team_names.values())
    else:
        fallback = getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')
        team_names = [fallback]

    q = Q()
    for name in team_names:
        q |= (
            Q(home_team__name__icontains=name) |
            Q(away_team__name__icontains=name) |
            Q(home_team_text__icontains=name) |
            Q(away_team_text__icontains=name)
        )
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
        from videosvoley.users.models import Membership
        qs = Membership.objects.filter(
            user=request.user,
            organization=tenant,
            is_approved=True,
        )
        if self.required_roles:
            qs = qs.filter(role__in=self.required_roles)
        if not qs.exists():
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class TenantManagerRequired(TenantMemberRequired):
    """Requiere role manager o admin en el tenant."""
    required_roles = ['manager', 'admin']


class TenantAdminRequired(TenantMemberRequired):
    """Requiere role admin en el tenant."""
    required_roles = ['admin']
