"""Backward-compatible re-export of RFEVB Celery tasks."""

from ilovevoley.competitions.tasks_rfevb import *  # noqa: F401,F403

__all__ = [
    'scrape_rfevb_competition',
    'scrape_rfevb_final_classification',
    'scrape_rfevb_fases',
]
