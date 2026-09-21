from .models import Season


def resolve_season_filter(request):
    """Temporada a filtrar según ?season=.

    Sin parámetro -> temporada activa; parámetro vacío -> todas; id -> esa.
    Si el id no existe, cae a la temporada activa.
    Devuelve (season_o_None, id_seleccionado_para_el_selector).
    """
    current = Season.objects.current()
    param = request.GET.get('season')
    if param is None:
        return current, (str(current.pk) if current else '')
    if param == '':
        return None, ''
    try:
        season = Season.objects.filter(pk=param).first()
    except (ValueError, TypeError):
        # `?season=abc` (o cualquier valor no numérico) no debe romper la vista.
        season = None
    if season is None:
        return current, (str(current.pk) if current else '')
    return season, str(season.pk)
