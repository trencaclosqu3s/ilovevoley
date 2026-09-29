"""Lectura y normalización de los parciales de un partido.

Fuentes, por prioridad: el acta oficial (juego real), los parciales guardados en
``Match.set_scores`` (scraping de resultados o entrada manual). El acta manda
cuando aporta parciales; si no, se usa ``set_scores``.
"""

from unidecode import unidecode


def extract_set_scores(
    lineup_data: dict, home_name: str, away_name: str
) -> list[tuple[int, int]]:
    """Extrae (pts_local, pts_visitante) por set emparejando por nombre."""

    def words(value: str) -> set[str]:
        normalized = unidecode(value or '').replace('-', ' ')
        return {word.lower() for word in normalized.split() if word}

    home_words, away_words = words(home_name), words(away_name)
    scores: list[tuple[int, int]] = []
    for set_data in lineup_data.get('sets') or []:
        home_points = away_points = None
        for team in set_data.get('teams') or []:
            points = team.get('points')
            if points is None:
                continue
            name_words = words(team.get('name') or '')
            home_match = len(name_words & home_words)
            away_match = len(name_words & away_words)
            if home_match > away_match:
                home_points = int(points)
            elif away_match > home_match:
                away_points = int(points)
        if home_points is not None and away_points is not None:
            scores.append((home_points, away_points))
    return scores


def normalize_set_scores(set_scores) -> list[tuple[int, int]]:
    """Normaliza ``[[25, 20], ...]`` a una lista de tuplas de enteros."""
    scores: list[tuple[int, int]] = []
    for score in set_scores or []:
        try:
            scores.append((int(score[0]), int(score[1])))
        except (TypeError, ValueError, IndexError):
            continue
    return scores


def match_set_scores(match) -> list[tuple[int, int]]:
    """Parciales a mostrar del partido: acta si aporta, si no ``set_scores``."""
    if match.acta_data is not None:
        acta_scores = extract_set_scores(
            match.acta_data,
            home_name=match.home_team_display,
            away_name=match.away_team_display,
        )
        if acta_scores:
            return acta_scores
    return normalize_set_scores(match.set_scores)
