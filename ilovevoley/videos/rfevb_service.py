"""Backward-compatible re-export of RFEVB scraping service."""

from ilovevoley.competitions.services.rfevb_service import *  # noqa: F401,F403
from ilovevoley.competitions.services.rfevb_service import (  # noqa: F401
    _build_team_map,
    _fetch_logo_map,
    _get_or_create_subleague,
    _process_match,
    _resolve_team,
    _update_standings,
)
