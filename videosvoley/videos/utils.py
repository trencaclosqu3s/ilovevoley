"""
Utilidades para el sistema de videos
"""
import html
import unicodedata
import re


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
    from .models import Team
    
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