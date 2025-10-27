"""
Tareas de Celery para scraping automático de datos de voleibol.
Las tareas han sido migradas a las nuevas apps específicas.
Este archivo mantiene las referencias para compatibilidad hacia atrás.
"""

# Importar tareas de las nuevas apps para compatibilidad
from videosvoley.competitions.tasks import (
    scrape_all_leagues_task,
    scrape_league_task,
    scrape_calendar_task,
    scrape_results_task,
    scrape_clubs_task,
    scrape_teams_task,
    handle_withdrawn_teams_task,
)

# Mantener las referencias para compatibilidad hacia atrás
__all__ = [
    'scrape_all_leagues_task',
    'scrape_league_task',
    'scrape_calendar_task',
    'scrape_results_task',
    'scrape_clubs_task',
    'scrape_teams_task',
    'handle_withdrawn_teams_task',
]