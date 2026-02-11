from django import template
from videosvoley.videos.models import Image

register = template.Library()

@register.simple_tag
def get_latest_images(limit=6):
    """Retorna las últimas imágenes aprobadas"""
    return Image.objects.filter(status='approved').order_by('-upload_date').select_related(
        'match__home_team', 'match__away_team', 'uploaded_by'
    )[:limit]
