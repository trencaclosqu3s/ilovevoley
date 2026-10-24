"""Marcas de jugada (#580) listas para mostrar: enlace ``&t=``, etiqueta de tiempo y clip."""
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse


def clip_filename(mark):
    """Nombre con el que el marcador publica el clip de la marca (voley-scoreboard#19).

    Sale solo de enteros de la BD: no hay ruta que venga de la petición.
    """
    return f'm{mark.match_id}_{mark.seconds}.mp4'


def _clip_path(mark):
    return Path(settings.SCOREBOARD_CLIPS_DIR) / clip_filename(mark)


def match_marks(match, video_id=''):
    """Marcas del partido con ``link`` (vacío sin ``video_id``), ``label`` y ``has_clip``.

    El enlace se construye siempre como ``watch?v=<id>``: ``youtu.be``, ``embed``
    y ``live`` no tienen ``?`` y el ``&t=`` no se interpretaría. Los clips los
    borra la retención del marcador: si el fichero ya no está, la marca se queda
    solo con el enlace al vídeo.
    """
    marks = list(match.marks.prefetch_related('persons'))
    for mark in marks:
        mark.link = f'https://www.youtube.com/watch?v={video_id}&t={mark.seconds}s' if video_id else ''
        mark.person_ids = {p.pk for p in mark.persons.all()}
        hours, rest = divmod(mark.seconds, 3600)
        mark.label = f'{hours}:{rest // 60:02d}:{rest % 60:02d}' if hours else f'{rest // 60}:{rest % 60:02d}'
        mark.has_clip = _clip_path(mark).is_file()
    return marks


def serve_mark_clip(mark):
    """Entrega el mp4 de una marca ya autorizada (``X-Accel-Redirect`` en producción)."""
    path = _clip_path(mark)
    if not path.is_file():
        raise Http404
    if getattr(settings, 'PROTECTED_MEDIA_USE_X_ACCEL', not settings.DEBUG):
        response = HttpResponse(content_type='video/mp4')
        response['X-Accel-Redirect'] = f'{settings.SCOREBOARD_CLIPS_INTERNAL_URL}{path.name}'
    else:
        response = FileResponse(path.open('rb'), content_type='video/mp4')
    response['Content-Disposition'] = f'attachment; filename="{path.name}"'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, no-store'
    return response
