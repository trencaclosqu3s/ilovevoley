from .rosters import Person, PlayerRole, StaffRole, person_photo_upload_path  # noqa: F401
from .legacy import (  # noqa: F401
    Player,
    Staff,
    player_photo_upload_path,
    staff_photo_upload_path,
)

__all__ = [
    'Person',
    'PlayerRole',
    'StaffRole',
    'Player',
    'Staff',
    'person_photo_upload_path',
    'player_photo_upload_path',
    'staff_photo_upload_path',
]
