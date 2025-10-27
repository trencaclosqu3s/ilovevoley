"""
Forms para la app videos.
Los forms han sido migrados a las nuevas apps específicas.
Este archivo mantiene las referencias para compatibilidad hacia atrás.
"""

# Importar forms de las nuevas apps para compatibilidad
from videosvoley.content.forms import (
    VideoForm,
    CommentForm,
    ImageUploadForm,
    ImageModerationForm,
    ImageFilterForm,
)

from videosvoley.competitions.forms import (
    MatchAdminForm,
    FriendlyMatchForm,
    MatchResultForm,
    LeagueForm,
    StandingForm,
)

from videosvoley.teams.forms import (
    TeamForm,
    ClubForm,
    TeamSearchForm,
    ClubSearchForm,
    TeamFilterForm,
    ClubFilterForm,
)

from videosvoley.rosters.forms import (
    PersonForm,
    PlayerRoleForm,
    StaffRoleForm,
    PersonSearchForm,
    PersonFilterForm,
    QuickPersonForm,
)

# Mantener las referencias para compatibilidad hacia atrás
__all__ = [
    # Content forms
    'VideoForm',
    'CommentForm',
    'ImageUploadForm',
    'ImageModerationForm',
    'ImageFilterForm',
    
    # Competitions forms
    'MatchAdminForm',
    'FriendlyMatchForm',
    'MatchResultForm',
    'LeagueForm',
    'StandingForm',
    
    # Teams forms
    'TeamForm',
    'ClubForm',
    'TeamSearchForm',
    'ClubSearchForm',
    'TeamFilterForm',
    'ClubFilterForm',
    
    # Rosters forms
    'PersonForm',
    'PlayerRoleForm',
    'StaffRoleForm',
    'PersonSearchForm',
    'PersonFilterForm',
    'QuickPersonForm',
]