"""Reexport de modelos legacy desde videosvoley.rosters para retrocompatibilidad."""
from videosvoley.rosters.models import (  # noqa: F401
    Player,
    Staff,
    player_photo_upload_path,
    staff_photo_upload_path,
)

__all__ = ['Player', 'Staff', 'player_photo_upload_path', 'staff_photo_upload_path']
