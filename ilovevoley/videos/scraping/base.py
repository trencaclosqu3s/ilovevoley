"""Módulo base para scraping: validaciones, excepciones y clase base."""

import logging
import re
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


def league_max_sets(league) -> int:
    """Máximo de sets del formato de una liga (para situar el set decisivo a 15)."""
    if league.match_format == 'alevin_balear':
        return 3
    if league.match_format == 'tournament_3sets':
        return 3
    if league.match_format == 'custom':
        return league.custom_max_sets or 5
    return 5


def validate_set_scores(set_scores, league) -> bool:
    """Valida los parciales de entrada manual según el formato de la liga.

    Regla: cada set lo gana quien alcanza 25 puntos (o 15 en el set decisivo)
    con 2 de diferencia. El set decisivo es el último y solo existe si el partido
    llega al máximo de sets del formato (5º en estándar, 3º en torneo/alevín).

    No se aplica al acta ni al scraping de resultados: son fuente oficial y se
    aceptan tal cual.
    """
    if not set_scores:
        return True

    max_sets = league_max_sets(league)
    total = len(set_scores)

    for index, score in enumerate(set_scores):
        try:
            home, away = int(score[0]), int(score[1])
        except (TypeError, ValueError, IndexError):
            return False
        if home < 0 or away < 0 or home == away:
            return False
        target = 15 if (total == max_sets and index == total - 1) else 25
        winner, loser = max(home, away), min(home, away)
        if winner < target or winner - loser < 2:
            return False

    home_won = sum(1 for home, away in set_scores if int(home) > int(away))
    away_won = total - home_won
    return validate_volleyball_score(home_won, away_won, league)


def parse_set_scores_string(value):
    """Convierte ``'25-10/25-15/25-11'`` en ``[[25, 10], [25, 15], [25, 11]]``.

    Devuelve ``None`` si no hay ningún parcial válido.
    """
    if not value:
        return None

    scores = []
    for chunk in str(value).split('/'):
        match = re.match(r'^(\d+)\s*-\s*(\d+)$', chunk.strip())
        if match:
            scores.append([int(match.group(1)), int(match.group(2))])
    return scores or None


def is_penalty_result(set_scores) -> bool:
    """Detecta un resultado por penalización/incomparecencia.

    Patrón: todos los sets con un mismo lado a 0 (p. ej. ``25-0/25-0/25-0``).
    """
    if not set_scores or len(set_scores) < 2:
        return False

    winners = set()
    for score in set_scores:
        try:
            home, away = int(score[0]), int(score[1])
        except (TypeError, ValueError, IndexError):
            return False
        if home == 0 and away == 0:
            return False
        if away == 0:
            winners.add('home')
        elif home == 0:
            winners.add('away')
        else:
            return False
    return len(winners) == 1


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
    'validate_set_scores',
    'league_max_sets',
    'parse_set_scores_string',
    'is_penalty_result',
    'ScrapingError',
    'BaseParser',
]
