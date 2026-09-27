from django.templatetags.static import static

from .tenant_utils import (
    build_tenant_url,
    get_tenant_base_domain,
)


def tenant_context(request):
    org = getattr(request, 'tenant', None)
    share_image_path = org.logo.url if org and org.logo else static('images/logo_app.png')
    
    is_manager = False
    is_admin = False
    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        if user.is_superuser:
            is_manager = True
            is_admin = True
        elif org:
            from ilovevoley.users.models import Membership
            membership = Membership.objects.filter(
                user=user,
                organization=org,
                is_approved=True,
            ).values_list('role', flat=True).first()
            if membership:
                is_manager = membership in ('manager', 'admin')
                is_admin = membership == 'admin'

    return {
        'tenant': org,
        'tenant_color': org.primary_color if org else '#9B7FBF',
        'tenant_color_dark': org.secondary_color if org else '#7B5FA0',
        'tenant_base_domain': get_tenant_base_domain(request),
        'build_tenant_url': lambda slug: build_tenant_url(slug, request),
        'tenant_share_image': request.build_absolute_uri(share_image_path),
        'can_moderate_memberships': is_manager,
        'is_tenant_manager': is_manager,
        'is_tenant_admin': is_admin,
    }
