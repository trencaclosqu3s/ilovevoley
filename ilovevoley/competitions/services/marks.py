"""Marcas de jugada (#580) listas para mostrar: enlace ``&t=`` y etiqueta de tiempo."""


def match_marks(match, base_url=''):
    """Marcas del partido con ``link`` (vacío si no hay vídeo al que apuntar) y ``label``."""
    marks = list(match.marks.prefetch_related('persons'))
    for mark in marks:
        mark.link = f'{base_url}&t={mark.seconds}s' if base_url else ''
        mark.person_ids = {p.pk for p in mark.persons.all()}
        hours, rest = divmod(mark.seconds, 3600)
        mark.label = f'{hours}:{rest // 60:02d}:{rest % 60:02d}' if hours else f'{rest // 60}:{rest % 60:02d}'
    return marks
