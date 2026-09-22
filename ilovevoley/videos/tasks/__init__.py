"""Tareas Celery de la app videos, repartidas por responsabilidad.

config/celery.py hace  para forzar
el registro. Las 16 tareas llevan name= explícito: ese nombre es el que
guardan las filas de PeriodicTask, y no debe cambiarse nunca.
"""

from .scraping import *  # noqa: F401,F403
from .enrichment import *  # noqa: F401,F403
from .rfevb import *  # noqa: F401,F403

__all__ = [
    # scraping (7)
    'scrape_all_leagues_task',
    'scrape_league_task',
    'scrape_calendar_task',
    'scrape_results_task',
    'scrape_clubs_task',
    'handle_withdrawn_teams_task',
    'scrape_teams_task',
    # enrichment (7)
    'enrich_matches_json_task',
    'enrich_single_league_json_task',
    'enrich_upcoming_matches_task',
    'scrape_and_enrich_all_task',
    'scrape_json_results_task',
    'scrape_json_upcoming_task',
    'process_json_unified_task',
    # rfevb (2 + 1 service re-export)
    'scrape_rfevb_competition',
    'scrape_rfevb_final_classification',
    'scrape_rfevb_fases',
]
