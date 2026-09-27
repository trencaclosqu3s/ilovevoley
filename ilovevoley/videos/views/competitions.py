from ilovevoley.competitions.views import *  # noqa: F401,F403
from ilovevoley.competitions.views import (
    ajax_acta_lineup,
    ajax_add_match_result,
    ajax_matches_by_category,
    ajax_search_teams,
    ajax_teams_by_league_category,
    calendar_view,
    friendly_match_create,
    league_detail,
    league_list,
    match_detail,
    match_result_card,
    standings_view,
)

__all__ = [
    'league_list',
    'league_detail',
    'match_detail',
    'match_result_card',
    'calendar_view',
    'friendly_match_create',
    'ajax_search_teams',
    'ajax_add_match_result',
    'ajax_acta_lineup',
    'standings_view',
    'ajax_matches_by_category',
    'ajax_teams_by_league_category',
]
