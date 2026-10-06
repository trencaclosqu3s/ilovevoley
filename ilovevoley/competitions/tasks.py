"""Tareas Celery de la app competitions."""
import logging
from datetime import time, timedelta

from celery import shared_task
from django.utils import timezone

from ilovevoley.competitions.models import Match
from ilovevoley.competitions.services.notifications import notify_match_reminder

logger = logging.getLogger(__name__)

# El scraper usa las 00:00 como "hora sin confirmar" (ver el merge de
# `federation.py`, "hora específica vs 00:00"). Esos partidos no deben recibir el
# recordatorio: caerían en la ventana a las ~22:00 del día anterior.
_UNCONFIRMED_HOUR = time(0, 0)


@shared_task(name='send_match_reminders_2h')
def send_match_reminders_2h_task():
    """Busca partidos programados que comienzan en torno a 2 horas y envía recordatorio push (#280).

    Ventana: partidos entre now + 1h45m y now + 2h15m con reminder_sent_at nulo
    y estado programado o en curso.
    """
    now = timezone.now()
    window_start = now + timedelta(minutes=105)
    window_end = now + timedelta(minutes=135)

    matches = (
        Match.objects.filter(
            status__in=['scheduled', 'in_progress'],
            match_date__gte=window_start,
            match_date__lte=window_end,
            reminder_sent_at__isnull=True,
        )
        .select_related('home_team', 'away_team', 'league')
        .prefetch_related('league__categories')
    )

    sent_count = 0
    for match in matches:
        if timezone.localtime(match.match_date).time() == _UNCONFIRMED_HOUR:
            continue
        try:
            if notify_match_reminder(match):
                sent_count += 1
        except Exception as e:
            logger.error(
                f"Error al enviar recordatorio push para el partido {match.id}: {e}",
                exc_info=True,
            )

    return sent_count


@shared_task(name='scrape_balearic_callups')
def scrape_balearic_callups_task(
    season_id=None,
    temp_override=None,
    force=False,
    no_notify=False,
):
    """Descarga y procesa convocatorias federativas de la selección balear (FVBIB)."""
    from ilovevoley.core.models import Season
    from ilovevoley.competitions.management.commands.scrape_balearic_callups import (
        run_balearic_callups_scrape,
    )

    season = None
    if season_id:
        try:
            season = Season.objects.get(pk=season_id)
        except Season.DoesNotExist:
            logger.error(f"Temporada {season_id} no encontrada para scrape_balearic_callups.")
            return {'processed': 0, 'error': f'Season {season_id} not found'}

    return run_balearic_callups_scrape(
        season=season,
        temp=temp_override,
        dry_run=False,
        force=force,
        no_notify=no_notify,
    )


@shared_task(name='scrape_balearic_tracking')
def scrape_balearic_tracking_task(
    season_id=None,
    temp_override=None,
    force=False,
    no_notify=False,
):
    """Descarga y procesa circulares de tecnificación y seguimiento federativo (FVBIB, #288)."""
    from ilovevoley.core.models import Season
    from ilovevoley.competitions.services.callup_ingestion import run_callups_scrape

    season = None
    if season_id:
        try:
            season = Season.objects.get(pk=season_id)
        except Season.DoesNotExist:
            logger.error(f"Temporada {season_id} no encontrada para scrape_balearic_tracking.")
            return {'processed': 0, 'error': f'Season {season_id} not found'}

    return run_callups_scrape(
        season=season,
        tipo=22,
        temp=temp_override,
        dry_run=False,
        force=force,
        no_notify=no_notify,
    )


@shared_task(name='discover_leagues')
def discover_leagues_task():
    """Busca en el menú federativo ligas nuevas de la temporada activa (#377).

    Las competiciones se publican escalonadas durante todo el año (categorías que
    llegan tarde, fases Oro/Plata, copas), así que debe ejecutarse a menudo.
    """
    from ilovevoley.competitions.services.discovery import discover
    from ilovevoley.core.models import Season

    return len(discover(Season.objects.current()))  # sin temporada, discover no hace nada
