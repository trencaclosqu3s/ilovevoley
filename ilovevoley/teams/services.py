"""Matching de equipos con su club federativo.

La lógica es pura (no toca el ORM) para poder reutilizarla desde el scraping,
el admin y las migraciones de backfill.
"""
from difflib import SequenceMatcher

from ilovevoley.videos.utils import normalize_team_name

# Umbral a partir del cual se aplica automáticamente un match.
MATCH_THRESHOLD = 0.55
# Umbral mínimo para considerar un club como candidato.
MIN_CANDIDATE_SCORE = 0.3

_STOPWORDS = {'club', 'volei', 'voley', 'voleibol', 'cv', 'esportiu', 'deportivo'}


def score_club_match(team_name, club_name):
    """Similitud [0, 1] entre el nombre de un equipo y el de un club."""
    team_normalized = normalize_team_name(team_name)
    club_normalized = normalize_team_name(club_name)
    if not team_normalized or not club_normalized:
        return 0.0

    similarity = SequenceMatcher(None, team_normalized, club_normalized).ratio()

    team_words = set(team_normalized.split())
    club_words = set(club_normalized.split())
    meaningful_common = (team_words & club_words) - _STOPWORDS
    if meaningful_common:
        word_similarity = len(meaningful_common) / max(len(team_words), len(club_words))
        similarity = max(similarity, word_similarity)

    return similarity


def find_best_club(team_name, clubs):
    """Devuelve ``(club, score)`` del mejor candidato o ``None``.

    ``clubs`` es cualquier iterable de objetos con atributo ``official_name``
    (incluidos los modelos históricos de una migración).
    """
    best_club = None
    best_score = 0.0

    for club in clubs:
        score = score_club_match(team_name, club.official_name)
        if score > best_score:
            best_club = club
            best_score = score

    if best_club is None or best_score < MIN_CANDIDATE_SCORE:
        return None
    return best_club, best_score
