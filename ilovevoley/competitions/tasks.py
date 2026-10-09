"""Tareas Celery de la app competitions."""
import logging
from datetime import time, timedelta
from time import sleep

from celery import shared_task
from django.utils import timezone

from ilovevoley.competitions.models import League, Match
from ilovevoley.competitions.services.notifications import notify_match_photo_reminder, notify_match_reminder

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


@shared_task(name='send_match_photo_reminders')
def send_match_photo_reminders_task():
    """Push para animar a subir fotos, 1 h después de registrarse el resultado (#361).

    Ancla: `result_notified_at` (lo fija `notify_match_result` al llegar el marcador,
    por scraping o a mano en amistosos). Se recogen los resultados de más de 1 h y
    menos de 7 días, así un retraso de Celery no pierde avisos; el flag
    `photo_reminder_sent_at` evita repetirlos. Un resultado editado solo en el
    admin no dispara el aviso.
    """
    now = timezone.now()
    matches = (
        Match.objects.filter(
            status='finished',
            result_notified_at__gte=now - timedelta(days=7),
            result_notified_at__lte=now - timedelta(hours=1),
            photo_reminder_sent_at__isnull=True,
        )
        .select_related('home_team', 'away_team', 'league')
        .prefetch_related('league__categories')
    )

    sent_count = 0
    for match in matches:
        try:
            if notify_match_photo_reminder(match):
                sent_count += 1
        except Exception as e:
            logger.error(
                f"Error al enviar recordatorio de fotos para el partido {match.id}: {e}",
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


@shared_task(name='scrape_federation_circulars')
def scrape_federation_circulars_task():
    """Indexa las circulares federativas de comité de competición y normas (FVBIB, #368)."""
    from ilovevoley.core.models import Season
    from ilovevoley.competitions.services.circulars_ingestion import run_circulars_scrape

    return run_circulars_scrape(Season.objects.current())


@shared_task(name='scrape_federation_news')
def scrape_federation_news_task():
    """Sincroniza las noticias federativas (FVBIB, #370)."""
    from ilovevoley.competitions.services.news_ingestion import run_news_scrape

    return run_news_scrape()


@shared_task(name='discover_leagues')
def discover_leagues_task():
    """Busca ligas nuevas de pista y vóley playa en la temporada activa (#377, #372).

    Las competiciones se publican escalonadas durante todo el año (categorías que
    llegan tarde, fases Oro/Plata, copas y torneos estivales de playa), así que
    debe ejecutarse a menudo. Solo avisa por email cuando hay candidatas nuevas,
    con enlace a la cola, solo a los destinatarios técnicos (``TECHNICAL_ALERT_EMAILS``)
    para no saturar a los demás superusers.
    """
    from django.urls import reverse
    from django.utils.translation import gettext as _

    from ilovevoley.competitions.services.discovery import discover, discover_seasonal_beach
    from ilovevoley.core.email_utils import get_technical_alert_emails, send_notification_email
    from ilovevoley.core.models import Season
    from ilovevoley.core.tenant_utils import build_absolute_url

    current = Season.objects.current()
    if current is None:
        return 0

    candidates = discover(current) + discover_seasonal_beach(current)
    if candidates:
        send_notification_email(
            subject=lambda: _('%(count)s nuevas ligas pendientes de validar') % {'count': len(candidates)},
            template_name='emails/league_candidates_pending.html',
            context={
                'candidates': candidates,
                'count': len(candidates),
                'site_name': 'I Love Voley',
                'admin_url': build_absolute_url(
                    reverse('admin:competitions_leaguecandidate_changelist') + '?status__exact=pending'
                ),
            },
            recipient_list=get_technical_alert_emails(),
        )
    return len(candidates)


@shared_task(name='discover_historical_leagues')
def discover_historical_leagues_task(seasons=5):
    """Propone candidatas históricas de las últimas ``seasons`` temporadas (#404).

    No crea ligas: deja ``LeagueCandidate`` pendientes con ``is_historical=True``
    para que el superuser elija en la cola cuáles sincroniza.
    """
    from ilovevoley.competitions.services.discovery import discover_historical
    from ilovevoley.core.models import Season

    base = Season.objects.current()
    if base is None:
        return 0
    past_seasons = [
        Season.objects.resolve(f'{base.start_year - i}-{base.start_year - i + 1}')
        for i in range(1, seasons + 1)
    ]
    return len(discover_historical(past_seasons))


@shared_task(name='scrape_historical_leagues')
def scrape_historical_leagues_task(league_ids, delay=2.0):
    """Scrapea una sola vez clasificación, calendario y resultados de ligas históricas (#404).

    Acepta ligas inactivas (las históricas lo son) y trae los marcadores con
    ``scrape_all_results_rounds``, que es lo que alimenta el H2H. Una liga caída
    no aborta el resto.
    """
    from ilovevoley.videos.scraping import FederationScraper

    summary = []
    leagues = list(League.objects.filter(pk__in=league_ids, is_historical=True))
    for i, league in enumerate(leagues):
        matches = 0
        try:
            scraper = FederationScraper(league)
            results = scraper.scrape_all_endpoints()
            matches += sum(len(data.get('matches', [])) for data in results.values() if 'error' not in data)
            matches += scraper.scrape_all_results_rounds(delay=delay).get('total_matches', 0)
        except Exception:  # noqa: BLE001 - una liga caída no debe abortar la ingesta
            logger.error('Error scrapeando la liga histórica %s', league.pk, exc_info=True)
        summary.append({'league_id': league.pk, 'matches': matches})
        if i < len(leagues) - 1:
            sleep(delay)
    return summary


@shared_task(name='discover_seasonal_beach_leagues')
def discover_seasonal_beach_leagues_task():
    """Descubre ligas de vóley playa en la ventana estacional de verano (#372)."""
    from ilovevoley.competitions.services.discovery import discover_seasonal_beach
    from ilovevoley.core.models import Season

    current = Season.objects.current()
    if current is None:
        return 0
    return len(discover_seasonal_beach(current))


# Actas por pasada: limita las peticiones a la federación y deja que el histórico
# pendiente se ponga al día en unas pocas ejecuciones.
ACTA_BATCH_SIZE = 50


@shared_task(name='scrape_match_actas')
def scrape_match_actas_task(limit=ACTA_BATCH_SIZE):
    """Guarda las actas de partidos oficiales de los tenants y enlaza alineaciones (#455).

    Hasta ahora el acta solo se guardaba si alguien la abría en el detalle del partido.
    Los partidos rival contra rival no se procesan: no hay jugadores de ningún tenant.
    Un acta que falla se reintenta en la siguiente pasada; si falla siempre (p. ej. HTML
    que el parser no entiende), ocupa un hueco del lote hasta que se corrija a mano.
    """
    import requests

    from ilovevoley.core.mixins import get_club_team_filter
    from ilovevoley.core.models import Organization
    from ilovevoley.core.security import UnsafeURL
    from ilovevoley.competitions.services.lineups import fetch_and_store_acta, relink_orphan_lineups

    tenant_q = None
    for organization in Organization.objects.filter(is_active=True):
        club_q = get_club_team_filter(organization)
        if club_q:
            tenant_q = club_q if tenant_q is None else tenant_q | club_q

    processed = failed = 0
    if tenant_q is not None:
        pending = (
            Match.objects.filter(tenant_q, status='finished', is_friendly=False, acta_data__isnull=True)
            .exclude(acta_html='')
            .select_related('home_team', 'away_team', 'league__season')
            .distinct()
            .order_by('-match_date')[:limit]
        )
        for match in pending:
            try:
                fetch_and_store_acta(match)
                processed += 1
            except (UnsafeURL, requests.exceptions.RequestException, ValueError) as exc:
                failed += 1
                logger.warning('No se pudo guardar el acta del partido %s: %s', match.id, exc)

    return {'processed': processed, 'failed': failed, 'relinked': relink_orphan_lineups()}
