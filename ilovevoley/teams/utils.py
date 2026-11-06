"""Utilidades para normalización y búsqueda de equipos."""
from difflib import SequenceMatcher
import html
import re
import unicodedata

__all__ = [
    'find_duplicate_team_by_name',
    'find_similar_team_by_name',
    'normalize_team_name',
]


def normalize_team_name(name):
    """
    Normaliza un nombre de equipo para comparación, manejando entidades HTML
    y caracteres especiales del catalán y español.

    Args:
        name (str): Nombre del equipo a normalizar

    Returns:
        str: Nombre normalizado para comparación
    """
    if not name:
        return ''

    # Convertir entidades HTML comunes a caracteres reales
    # Manejar casos específicos como #39; -> ', &apos; -> ', etc.
    normalized = name

    # Reemplazar entidades HTML comunes manualmente antes de html.unescape
    html_entities = {
        '&#39;': "'",
        '#39;': "'",
        '&apos;': "'",
        '&quot;': '"',
        '&amp;': '&',
        '&lt;': '<',
        '&gt;': '>',
        '&nbsp;': ' ',
    }

    for entity, char in html_entities.items():
        normalized = normalized.replace(entity, char)

    # Luego usar html.unescape para el resto
    normalized = html.unescape(normalized)

    # Quitar acentos y diacríticos
    normalized = unicodedata.normalize('NFD', normalized)
    normalized = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')

    # Convertir a mayúsculas y limpiar espacios
    normalized = normalized.upper().strip()

    # Quitar caracteres especiales pero mantener apóstrofes, guiones y espacios
    # Esto preserva caracteres importantes del catalán como la ç, ñ, etc.
    normalized = re.sub(r'[^\w\s\'-]', ' ', normalized)
    normalized = ' '.join(normalized.split())

    return normalized


def find_duplicate_team_by_name(team_name, category=None, exclude_id=None):
    """
    Busca equipos duplicados por nombre normalizado.

    Args:
        team_name (str): Nombre del equipo a buscar
        category: Categoría a filtrar (opcional)
        exclude_id: ID del equipo a excluir de la búsqueda (opcional)

    Returns:
        Team: Equipo duplicado encontrado o None
    """
    from ilovevoley.teams.models import Team

    normalized_name = normalize_team_name(team_name)

    # Buscar equipos con el mismo nombre normalizado
    teams = Team.objects.all()
    if category:
        teams = teams.filter(category=category)
    if exclude_id:
        teams = teams.exclude(id=exclude_id)

    for team in teams:
        if normalize_team_name(team.name) == normalized_name:
            return team

    return None


def find_similar_team_by_name(team_name, category=None, threshold=0.85, exclude_id=None):
    """
    Busca equipos con nombres similares usando similitud de secuencia (Levenshtein).
    Útil para detectar cambios leves en nombres (ej: typos, cambio de patrocinador menor)

    Args:
        team_name (str): Nombre del equipo a buscar
        category: Categoría a filtrar (opcional)
        threshold (float): Umbral de similitud (0.0 a 1.0)
        exclude_id: ID del equipo a excluir de la búsqueda

    Returns:
        tuple: (Team, score) o (None, 0)
    """
    from difflib import SequenceMatcher
    from ilovevoley.teams.models import Team

    normalized_target = normalize_team_name(team_name)
    best_match = None
    best_score = 0

    # Obtener candidatos (optimización: filtrar por longitud similar si hay muchos)
    teams = Team.objects.all()
    if category:
        teams = teams.filter(category=category)
    if exclude_id:
        teams = teams.exclude(id=exclude_id)

    for team in teams:
        normalized_current = normalize_team_name(team.name)

        # Calcular similitud
        ratio = SequenceMatcher(None, normalized_target, normalized_current).ratio()

        if ratio > best_score and ratio >= threshold:
            best_score = ratio
            best_match = team

    return best_match, best_score
