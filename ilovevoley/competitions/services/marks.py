"""Marcas de jugada (#580) listas para mostrar: enlace ``&t=`` y etiqueta de tiempo."""


def match_marks(match, video_id=''):
    """Marcas del partido con ``link`` (vacío sin ``video_id``) y ``label``.

    El enlace se construye siempre como ``watch?v=<id>``: ``youtu.be``, ``embed``
    y ``live`` no tienen ``?`` y el ``&t=`` no se interpretaría.
    """
    marks = list(match.marks.prefetch_related('persons'))
    for mark in marks:
        mark.link = f'https://www.youtube.com/watch?v={video_id}&t={mark.seconds}s' if video_id else ''
        mark.person_ids = {p.pk for p in mark.persons.all()}
        hours, rest = divmod(mark.seconds, 3600)
        mark.label = f'{hours}:{rest // 60:02d}:{rest % 60:02d}' if hours else f'{rest // 60}:{rest % 60:02d}'
    return marks
