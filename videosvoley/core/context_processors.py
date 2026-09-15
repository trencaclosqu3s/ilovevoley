from django.templatetags.static import static

from .tenant_utils import build_tenant_url, get_tenant_base_domain


def tenant_context(request):
    org = getattr(request, 'tenant', None)
    share_image_path = org.logo.url if org and org.logo else static('images/logo_app.png')
    return {
        'tenant': org,
        'tenant_color': org.primary_color if org else '#9B7FBF',
        'tenant_color_dark': org.secondary_color if org else '#7B5FA0',
        'tenant_base_domain': get_tenant_base_domain(request),
        'build_tenant_url': lambda slug: build_tenant_url(slug, request),
        'tenant_share_image': request.build_absolute_uri(share_image_path),
    }
