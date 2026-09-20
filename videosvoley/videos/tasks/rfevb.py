"""Tareas de scraping RFEVB (Campeonatos Nacionales)."""

import logging
import sys

from celery import shared_task

from videosvoley.videos.rfevb_service import (
    scrape_rfevb_fases,
    scrape_rfevb_final_classification as _scrape_final_classification,
)
from ..models import League, Match

logger = logging.getLogger(__name__)


@shared_task(name='scrape_rfevb_competition', bind=False)
def scrape_rfevb_competition(competition_id, fase_ids, parent_league_id):
    """
    Scraping de todas las fases de un campeonato RFEVB.

    Tras el scraping, si no quedan partidos pendientes bajo la liga padre,
    lanza scrape_rfevb_final_classification para cargar la clasificación general.

    Uso:
        scrape_rfevb_competition.delay(9041, [2193, 2194, 2195, 2196], 'ceim_2526')
    """
    _tasks = sys.modules.get('videosvoley.videos.tasks')
    _scrape_fases_func = getattr(_tasks, 'scrape_rfevb_fases', scrape_rfevb_fases)
    _final_class_func = getattr(_tasks, 'scrape_rfevb_final_classification', scrape_rfevb_final_classification)

    result = _scrape_fases_func(competition_id, fase_ids, parent_league_id)
    logger.info(f'RFEVB scraping completado: {result}')

    if 'error' in result:
        return result

    try:
        parent = League.objects.get(federation_id=parent_league_id)
        pending = Match.objects.filter(
            league__parent_league=parent,
            status='scheduled',
        ).exists()
        if not pending:
            logger.info('Todos los partidos finalizados, lanzando clasificación final')
            _final_class_func.delay(competition_id, parent_league_id)
    except League.DoesNotExist:
        logger.error(f'Liga padre no encontrada para trigger final: {parent_league_id}')

    return result


@shared_task(name='scrape_rfevb_final_classification', bind=False)
def scrape_rfevb_final_classification(competition_id, parent_league_id):
    """
    Scraping de la clasificación general final de una competición RFEVB.

    Parsea webCompeticion-clasificacion.php?IdCompeticion={id}.
    Se activa automáticamente desde scrape_rfevb_competition cuando todos
    los partidos están finalizados.

    NOTA: El parser de clasificación final se implementará cuando el torneo
    tenga datos reales (la página devuelve vacío antes de que termine).
    """
    result = _scrape_final_classification(competition_id, parent_league_id)
    logger.info(f'RFEVB clasificación final: {result}')
    return result


__all__ = [
    'scrape_rfevb_competition',
    'scrape_rfevb_final_classification',
    'scrape_rfevb_fases',
]
