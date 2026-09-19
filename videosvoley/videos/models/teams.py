"""Reexport de modelos de teams desde videosvoley.teams para retrocompatibilidad."""
from videosvoley.teams.models import Club, Team  # noqa: F401

__all__ = ['Club', 'Team']
