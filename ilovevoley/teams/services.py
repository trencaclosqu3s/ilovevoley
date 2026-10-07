"""Matching de equipos con su club federativo.

El club de un equipo sale de los ids de club que la federación (voleibolib) manda
en sus partidos, nunca del nombre (#380). Las funciones reciben los modelos para
poder reutilizarse con los modelos históricos de una migración.
"""
from collections import defaultdict
from difflib import SequenceMatcher

from ilovevoley.videos.utils import normalize_team_name

# Ids de club vacíos tal como los guarda el parser (``str(None)`` incluido).
EMPTY_CLUB_IDS = {'', 'None', '0'}


def federation_club_ids_by_team(match_model):
    """``{team_id: federation_id del club}`` según los partidos de cada equipo.

    Un equipo cuyos partidos apuntan a más de un club se descarta: ante la duda,
    sin club y revisión manual.
    """
    club_ids = defaultdict(set)
    matches = match_model._base_manager.all()
    for side, field in (('home_team_id', 'federation_club_local_id'), ('away_team_id', 'federation_club_away_id')):
        for team_id, club_id in matches.values_list(side, field).distinct():
            if team_id and club_id not in EMPTY_CLUB_IDS:
                club_ids[team_id].add(club_id)
    return {team_id: ids.pop() for team_id, ids in club_ids.items() if len(ids) == 1}


def resolve_team_clubs(match_model, club_model):
    """``{team_id: Club}`` de los equipos con un club federativo inequívoco."""
    club_ids = federation_club_ids_by_team(match_model)
    clubs = club_model._base_manager.in_bulk(set(club_ids.values()), field_name='federation_id')
    return {team_id: clubs[club_id] for team_id, club_id in club_ids.items() if club_id in clubs}


# Matching difuso por nombre: solo lo usa la migración 0003, que no se puede
# editar. No usarlo para asignar clubes (emparejaba CV Mataró con Club Mayurqa).

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


def cache_logo(obj):
    """Descarga el escudo de un ``Club``/``Team``, lo normaliza y lo guarda en ``obj.logo``.

    Devuelve True si guardó la copia. Si la descarga falla o la imagen no es
    válida no toca nada: ``display_logo`` sigue sirviendo la URL de la federación.
    Un equipo sin ``logo_url`` hereda el escudo de su club y no se descarga nada.
    """
    from django.core.files.base import ContentFile

    from ilovevoley.competitions.result_card import fetch_logo_bytes
    from ilovevoley.core.image_utils import normalize_crest

    url = obj.logo_url or getattr(obj, 'logo_federation_url', None)
    raw = fetch_logo_bytes(url, timeout=15)
    png = normalize_crest(raw) if raw else None
    if png is None:
        return False
    obj.logo.save(f'{obj.pk}.png', ContentFile(png), save=False)
    obj.save(update_fields=['logo'])
    return True
