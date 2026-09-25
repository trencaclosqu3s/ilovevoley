"""Reexport de modelos de teams desde ilovevoley.teams para retrocompatibilidad."""
from ilovevoley.teams.models import Club, Team  # noqa: F401

__all__ = ['Club', 'Team']
