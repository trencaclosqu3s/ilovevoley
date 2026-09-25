from ilovevoley.rosters.views import *  # noqa: F401,F403
from ilovevoley.rosters.views import (
    person_create,
    person_detail,
    person_edit,
    person_list,
    player_role_create,
    player_role_edit,
    player_role_toggle_active,
    roster_overview,
    staff_role_create,
    staff_role_edit,
    staff_role_toggle_active,
)

__all__ = [
    'roster_overview',
    'person_list',
    'person_detail',
    'person_create',
    'person_edit',
    'player_role_create',
    'staff_role_create',
    'player_role_edit',
    'staff_role_edit',
    'player_role_toggle_active',
    'staff_role_toggle_active',
]
