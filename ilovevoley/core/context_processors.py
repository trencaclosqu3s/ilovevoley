from django.templatetags.static import static

from .tenant_utils import (
    build_absolute_url,
    build_tenant_url,
    get_tenant_base_domain,
    hex_to_rgb_channels,
)

DEFAULT_BRAND = '#01696f'
DEFAULT_BRAND_DARK = '#004d52'
SANT_JOSEP_YELLOW = '#F4D47C'


def tenant_context(request):
    org = getattr(request, 'tenant', None)
    share_image_path = org.logo.url if org and org.logo else static('images/logo_app.png')

    if org:
        brand = org.primary_color if org.primary_color else DEFAULT_BRAND
        brand_dark = org.secondary_color if org.secondary_color else DEFAULT_BRAND_DARK
        gradient_from = brand
        # Sant Josep mantiene su identidad histórica morado→amarillo (#297).
        if getattr(org, 'slug', None) == 'santjosep':
            gradient_to = SANT_JOSEP_YELLOW
        else:
            gradient_to = org.secondary_color or brand
    else:
        brand = DEFAULT_BRAND
        brand_dark = DEFAULT_BRAND_DARK
        gradient_from = DEFAULT_BRAND
        gradient_to = DEFAULT_BRAND_DARK
    
    is_manager = False
    is_admin = False
    approved_memberships = []
    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        if user.is_superuser:
            is_manager = True
            is_admin = True
        if org:
            from ilovevoley.users.models import Membership
            # Solo cuentan las membresías de clubes activos: la landing únicamente
            # lista organizaciones activas, así que no ofrecemos un cambio a un
            # club que ya no es accesible.
            approved_memberships = list(
                Membership.objects.filter(
                    user=user,
                    is_approved=True,
                    organization__is_active=True,
                ).values_list('organization_id', 'role')
            )
            if not user.is_superuser:
                role = next(
                    (r for org_id, r in approved_memberships if org_id == org.id), None
                )
                if role:
                    is_manager = role in ('manager', 'admin')
                    is_admin = role == 'admin'

    # Solo tiene sentido ofrecer el cambio de club a quien pertenece a más de
    # una organización; el enlace apunta al dominio raíz, que ya lista los
    # clubes y reutiliza la selección de la landing.
    can_switch_club = len(approved_memberships) > 1

    return {
        'can_switch_club': can_switch_club,
        'switch_club_url': build_absolute_url('', request=request),
        'tenant': org,
        'tenant_color': brand,
        'tenant_color_dark': brand_dark,
        'tenant_color_rgb': hex_to_rgb_channels(brand, '1 105 111'),
        'tenant_color_dark_rgb': hex_to_rgb_channels(brand_dark, '0 77 82'),
        'tenant_gradient_from': gradient_from,
        'tenant_gradient_to': gradient_to,
        'tenant_gradient_from_rgb': hex_to_rgb_channels(gradient_from, '1 105 111'),
        'tenant_gradient_to_rgb': hex_to_rgb_channels(gradient_to, '0 77 82'),
        'tenant_base_domain': get_tenant_base_domain(request),
        'build_tenant_url': lambda slug: build_tenant_url(slug, request),
        'tenant_share_image': request.build_absolute_uri(share_image_path),
        'can_moderate_memberships': is_manager,
        'is_tenant_manager': is_manager,
        'is_tenant_admin': is_admin,
    }
