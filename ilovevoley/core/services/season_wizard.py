"""Servicio del wizard de nueva temporada.

La temporada activa es global y única, así que este wizard es una operación de
plataforma (superuser), no por tenant. Crea/activa la temporada y archiva las
ligas "main" de la temporada saliente para que dejen de aparecer por defecto,
sin borrar nada: el histórico sigue consultable (el detalle de liga solo exige
``is_active`` y la clasificación admite ``?season_name=``).
"""
from django.db import transaction

from ilovevoley.competitions.models import League
from ilovevoley.core.models import Season, normalize_season_name


def _marked_current():
    """Temporada marcada explícitamente como activa (no el fallback por fecha)."""
    return Season.objects.filter(is_current=True).first()


def preview_season(raw):
    """Resumen (dry-run) de lo que haría ``start_season``, sin escribir nada.

    Devuelve ``{'valid': False}`` si el nombre no tiene formato de temporada.
    """
    name = normalize_season_name(raw)
    if not name:
        return {'valid': False, 'name': None}

    start_year = int(name.split('-')[0])
    existing = Season.objects.filter(name=name).first()
    current = _marked_current()
    outgoing = current if (current and current.name != name) else None

    leagues_to_archive = 0
    if outgoing is not None:
        leagues_to_archive = League.objects.filter(
            season=outgoing, visibility_type='main', is_active=True,
        ).count()

    return {
        'valid': True,
        'name': name,
        'start_year': start_year,
        'end_year': start_year + 1,
        'season': existing,
        'is_new': existing is None,
        'already_current': bool(existing and existing.is_current),
        'current_season': current,
        'outgoing_season': outgoing,
        'leagues_to_archive': leagues_to_archive,
    }


@transaction.atomic
def start_season(raw):
    """Crea (si hace falta) la temporada, la activa y archiva las ligas salientes.

    Idempotente: relanzar con la misma temporada no duplica filas ni rearchiva
    ligas ya archivadas. Devuelve el resumen de ``preview_season`` ampliado con
    ``archived_leagues``.
    """
    summary = preview_season(raw)
    if not summary['valid']:
        raise ValueError('Formato de temporada no válido')

    archived = 0
    outgoing = summary['outgoing_season']
    if outgoing is not None:
        archived = League.objects.filter(
            season=outgoing, visibility_type='main', is_active=True,
        ).update(visibility_type='historical', is_historical=True)

    season = Season.objects.resolve(summary['name'])
    if not season.is_current:
        season.is_current = True
        season.save(update_fields=['is_current'])

    summary['season'] = season
    summary['archived_leagues'] = archived
    return summary
