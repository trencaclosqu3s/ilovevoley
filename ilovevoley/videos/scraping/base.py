"""Módulo base para scraping: validaciones, excepciones y clase base."""

import logging
import time
from typing import Any, Dict

import requests

from ..models import League

logger = logging.getLogger(__name__)


def validate_volleyball_score(home_score: int, away_score: int, league) -> bool:
    """
    Valida si un resultado de voleibol es válido según el formato de la liga.
    
    Args:
        home_score: Puntos del equipo local
        away_score: Puntos del equipo visitante
        league: Objeto League con el formato de partido configurado
    
    Returns:
        bool: True si el resultado es válido, False en caso contrario
    """
    # Resultados imposibles en cualquier formato
    impossible_scores = [(0, 0), (1, 1), (2, 2)]
    if (home_score, away_score) in impossible_scores:
        logger.warning(f"Resultado imposible detectado: {home_score}-{away_score}")
        return False
    
    if league.match_format == 'standard':
        # 5 sets máximo, ganar 3
        return (home_score == 3 and away_score < 3) or (away_score == 3 and home_score < 3)
    
    elif league.match_format == 'alevin_balear':
        # 3 sets, jugar los 3 - resultados posibles: 3-0, 2-1, 1-2, 0-3
        valid_alevin_scores = [
            (3, 0), (2, 1), (1, 2), (0, 3)
        ]
        return (home_score, away_score) in valid_alevin_scores
    
    elif league.match_format == 'tournament_3sets':
        # 3 sets máximo, ganar 2
        return (home_score == 2 and away_score < 2) or (away_score == 2 and home_score < 2)
    
    elif league.match_format == 'custom':
        # Usar valores personalizados
        max_sets = league.custom_max_sets or 5
        sets_to_win = league.custom_sets_to_win or 3
        return (home_score == sets_to_win and away_score < sets_to_win) or \
               (away_score == sets_to_win and home_score < sets_to_win)
    
    # Fallback para ligas sin formato definido (compatibilidad)
    return (home_score == 3 and away_score < 3) or (away_score == 3 and home_score < 3)


class ScrapingError(Exception):
    """Exception específica para errores de scraping"""
    pass


class BaseParser:
    """Clase base para todos los parsers"""
    
    def __init__(self, league: League):
        self.league = league
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
    
    def fetch_content(self, url: str) -> str:
        """Obtiene el contenido de una URL con manejo de errores"""
        try:
            logger.info(f"Fetching content from: {url}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logger.error(f"Error fetching {url}: {e}")
            raise ScrapingError(f"Failed to fetch {url}: {e}")
    
    def parse_content(self, content: str) -> Dict[str, Any]:
        """Método abstracto que debe implementar cada parser específico"""
        raise NotImplementedError("Subclasses must implement parse_content")
    
    def rate_limit(self, delay: float = 1.0):
        """Aplicar rate limiting entre requests"""
        time.sleep(delay)




__all__ = [
    'validate_volleyball_score',
    'ScrapingError',
    'BaseParser',
]
