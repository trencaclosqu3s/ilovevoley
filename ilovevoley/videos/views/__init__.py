"""Vistas de la app videos, repartidas por dominio.

urls.py importa este paquete y espera encontrar aquí todos los nombres de
vista que referencia. Ver el contrato en la Task 12 del plan de refactor.
"""

from .content import *  # noqa: F401,F403
from .moderation import *  # noqa: F401,F403
from .competitions import *  # noqa: F401,F403
from .teams import *  # noqa: F401,F403
from .rosters import *  # noqa: F401,F403
from .pages import *  # noqa: F401,F403

__all__ = [
    # content (11)
    'video_list',
    'video_create',
    'video_bulk_create',
    'video_detail',
    'image_gallery',
    'image_gallery_albums',
    'image_upload',
    'image_bulk_upload',
    'image_detail',
    'match_images',
    'album_group_images',
    # moderation (8)
    'image_moderation',
    'image_moderate_action',
    'image_moderate_bulk',
    'moderation_counts_api',
    'moderation_panel',
    'approve_user_api',
    'reject_user_api',
    'moderate_image_api',
    # competitions (11)
    'league_list',
    'league_detail',
    'match_detail',
    'calendar_view',
    'friendly_match_create',
    'ajax_search_teams',
    'ajax_add_match_result',
    'ajax_acta_lineup',
    'standings_view',
    'ajax_matches_by_category',
    'ajax_teams_by_league_category',
    # teams (3)
    'ajax_register_team',
    'team_list',
    'team_roster',
    # rosters (11)
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
    # pages (1)
    'about',
]
