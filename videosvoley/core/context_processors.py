def tenant_context(request):
    org = getattr(request, 'tenant', None)
    return {
        'tenant': org,
        'tenant_color': org.primary_color if org else '#9B7FBF',
        'tenant_color_dark': org.secondary_color if org else '#7B5FA0',
    }
