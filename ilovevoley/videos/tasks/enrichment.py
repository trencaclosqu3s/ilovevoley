"""Backward-compatible re-export of enrichment Celery tasks."""

from ilovevoley.competitions.tasks_enrichment import *  # noqa: F401,F403

__all__ = [
    'enrich_matches_json_task',
    'enrich_single_league_json_task',
    'enrich_upcoming_matches_task',
    'scrape_and_enrich_all_task',
    'scrape_json_results_task',
    'scrape_json_upcoming_task',
    'process_json_unified_task',
    'cache_federation_logos_task',
]
