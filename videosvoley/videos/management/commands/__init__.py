"""
Management commands para la app videos.
Los commands han sido migrados a las nuevas apps específicas.
Este archivo mantiene las referencias para compatibilidad hacia atrás.
"""

# Importar commands de las nuevas apps para compatibilidad
from videosvoley.competitions.management.commands import (
    scrape_all_leagues,
    scrape_league,
    scrape_teams,
    scrape_clubs,
    setup_league,
    scrape_external_leagues,
    scrape_historical_leagues,
)

from videosvoley.content.management.commands import (
    autotag_images,
)

from videosvoley.teams.management.commands import (
    clean_duplicate_teams,
)

from videosvoley.core.management.commands import (
    fix_match_timezones,
)

# Mantener las referencias para compatibilidad hacia atrás
__all__ = [
    'scrape_all_leagues',
    'scrape_league', 
    'scrape_teams',
    'scrape_clubs',
    'setup_league',
    'scrape_external_leagues',
    'scrape_historical_leagues',
    'autotag_images',
    'clean_duplicate_teams',
    'fix_match_timezones',
]