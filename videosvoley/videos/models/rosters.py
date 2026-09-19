"""Reexport de modelos de rosters desde videosvoley.rosters para retrocompatibilidad."""
from videosvoley.rosters.models import Person, PlayerRole, StaffRole, person_photo_upload_path  # noqa: F401

__all__ = ['Person', 'PlayerRole', 'StaffRole', 'person_photo_upload_path']