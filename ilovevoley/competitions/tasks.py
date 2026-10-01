"""Tareas Celery de la app competitions."""
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from ilovevoley.competitions.models import Match
from ilovevoley.competitions.services.notifications import notify_match_reminder

logger = logging.getLogger(__name__)


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
        try:
            if notify_match_reminder(match):
                sent_count += 1
        except Exception as e:
            logger.error(
                f"Error al enviar recordatorio push para el partido {match.id}: {e}",
                exc_info=True,
            )

    return sent_count
