"""Modelos de la app videos, repartidos por dominio.

Este paquete reexporta todos los nombres públicos que antes vivían en
models.py. No eliminar reexportaciones sin comprobar antes los 84 imports
del proyecto y las migraciones 0012, 0015, 0019 y 0020, que referencian
las funciones de upload por su ruta en este paquete.
"""

from .category import Category
from .teams import Club, Team
from .content import Comment, Image, Video, image_upload_path
from .competitions import (
    League,
    LeagueManager,
    Match,
    MatchAllManager,
    MatchManager,
    ScrapingEndpoint,
    Standing,
)
from .rosters import Person, PlayerRole, StaffRole, person_photo_upload_path
from .legacy import (
    Player,
    Staff,
    player_photo_upload_path,
    staff_photo_upload_path,
)

__all__ = [
    'Category',
    'Club',
    'Comment',
    'Image',
    'League',
    'LeagueManager',
    'Match',
    'MatchAllManager',
    'MatchManager',
    'Person',
    'Player',
    'PlayerRole',
    'ScrapingEndpoint',
    'Staff',
    'StaffRole',
    'Standing',
    'Team',
    'Video',
    'image_upload_path',
    'person_photo_upload_path',
    'player_photo_upload_path',
    'staff_photo_upload_path',
]
