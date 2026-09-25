from django import template
from ilovevoley.videos.models import Image

register = template.Library()

@register.simple_tag
def get_latest_images(limit=6, organization=None):
    qs = Image.objects.filter(status='approved')
    if organization:
        qs = qs.filter(organization=organization)
    return qs.order_by('-upload_date').select_related(
        'match__home_team', 'match__away_team', 'uploaded_by'
    )[:limit]
