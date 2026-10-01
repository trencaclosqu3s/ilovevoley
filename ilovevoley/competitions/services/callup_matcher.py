import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any
from ilovevoley.core.models import Organization, Season
from ilovevoley.rosters.models import Person


def _remove_accents(text: str) -> str:
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def _clean_text(text: str) -> str:
    return _remove_accents(text).upper().strip()


def _tokenize(text: str) -> list[str]:
    cleaned = _clean_text(text)
    return [t for t in re.split(r'[\s\-_,.]+', cleaned) if t]


def _normalize_club_name(name: str) -> str:
    cleaned = _clean_text(name)
    # Eliminar prefijos y palabras comunes de voleibol
    prefixes = [
        r'\bC\.?V\.?\b',
        r'\bCLUB\s+VOLEIBOL\b',
        r'\bCLUB\s+VOLEI\b',
        r'\bV\.?C\.?\b',
        r'\bVOLEIBOL\b',
        r'\bVOLEI\b',
        r'\bCLUB\b',
        r'\bA\.?D\.?\b',
    ]
    for pref in prefixes:
        cleaned = re.sub(pref, '', cleaned)
    return ' '.join(_tokenize(cleaned))


def _club_matches(raw_club: str, org: Organization) -> bool:
    norm_raw = _normalize_club_name(raw_club)
    if not norm_raw:
        return False

    raw_tokens = set(_tokenize(norm_raw))

    # Recoger candidatos de la organización
    candidates: list[str] = [org.name]
    if hasattr(org, 'club') and org.club:
        cand_name = getattr(org.club, 'official_name', None) or getattr(org.club, 'name', None)
        if cand_name:
            candidates.append(cand_name)

    if org.club_team_names and isinstance(org.club_team_names, dict):
        candidates.extend(str(v) for v in org.club_team_names.values())
        candidates.extend(str(k) for k in org.club_team_names.keys())

    for cand in candidates:
        norm_cand = _normalize_club_name(cand)
        if not norm_cand:
            continue
        cand_tokens = set(_tokenize(norm_cand))

        # Coincidencia por subconjunto de tokens significativos
        if raw_tokens and cand_tokens:
            if raw_tokens.issubset(cand_tokens) or cand_tokens.issubset(raw_tokens):
                return True

        # Similitud difusa
        if SequenceMatcher(None, norm_raw, norm_cand).ratio() >= 0.75:
            return True

    return False


def match_callup_player(player_data: dict[str, Any], season: Season) -> dict[str, Any]:
    """
    Cruza los datos de un jugador extraído del PDF con las plantillas del club.
    Retorna:
      - match_status: 'confirmed' | 'suspected' | 'rejected' | 'unmatched'
      - match_score: float (0.0 a 1.0)
      - organization: Organization | None
      - person: Person | None
      - match_notes: str
    """
    raw_club = (player_data.get('club') or '').strip()
    raw_first = (player_data.get('first_name') or '').strip()
    raw_last = (player_data.get('last_name') or '').strip()
    raw_year = player_data.get('birth_year')

    all_orgs = list(Organization.objects.select_related('club').all())
    matched_orgs = [org for org in all_orgs if _club_matches(raw_club, org)]

    raw_first_tokens = _tokenize(raw_first)
    raw_last_tokens = _tokenize(raw_last)

    def evaluate_person(person: Person) -> tuple[float, bool, str]:
        p_first_tokens = _tokenize(person.first_name)
        p_last_tokens = _tokenize(person.last_name)

        # 1. Puntuación de nombre de pila
        if not raw_first_tokens or not p_first_tokens:
            first_score = 0.0
        elif raw_first_tokens[0] == p_first_tokens[0]:
            first_score = 1.0
        elif set(raw_first_tokens).issubset(set(p_first_tokens)) or set(p_first_tokens).issubset(set(raw_first_tokens)):
            first_score = 1.0
        else:
            first_score = SequenceMatcher(
                None,
                _clean_text(raw_first),
                _clean_text(person.first_name)
            ).ratio()

        # 2. Puntuación de apellidos
        if not raw_last_tokens or not p_last_tokens:
            last_score = 0.0
        elif raw_last_tokens == p_last_tokens:
            last_score = 1.0
        elif len(raw_last_tokens) == 1 and raw_last_tokens[0] == p_last_tokens[0]:
            # Solo aportó el primer apellido y coincide exactamente
            last_score = 0.95
        elif set(raw_last_tokens).issubset(set(p_last_tokens)):
            last_score = 0.95
        else:
            last_score = SequenceMatcher(
                None,
                _clean_text(raw_last),
                _clean_text(person.last_name)
            ).ratio()

        base_score = (first_score * 0.40) + (last_score * 0.60)

        # 3. Validación de año de nacimiento
        year_match = False
        notes = []
        if raw_year and person.birth_date:
            if raw_year == person.birth_date.year:
                year_match = True
                notes.append(f'Año {raw_year} confirmado')
            elif abs(raw_year - person.birth_date.year) > 1:
                base_score = max(0.0, base_score - 0.30)
                notes.append(f'Descuadre año: PDF {raw_year} vs ficha {person.birth_date.year}')

        note_str = '; '.join(notes)
        return base_score, year_match, note_str

    best_match: dict[str, Any] = {
        'match_status': 'unmatched',
        'match_score': 0.0,
        'organization': None,
        'person': None,
        'match_notes': '',
    }

    # 1. Búsqueda en organizaciones donde el club coincide
    for org in matched_orgs:
        # Priorizar jugadores con rol activo en la temporada
        candidates = list(
            Person.objects.filter(
                organization=org,
                player_roles__season=season,
                player_roles__is_active=True,
            ).distinct()
        )
        # Si no hay con rol activo, mirar todas las personas de la organización
        if not candidates:
            candidates = list(Person.objects.filter(organization=org))

        for person in candidates:
            score, year_match, notes = evaluate_person(person)
            if score > best_match['match_score']:
                # Clasificación con club coincidente
                if score >= 0.85:
                    status = 'confirmed'
                elif score >= 0.70 or (score >= 0.65 and year_match):
                    status = 'confirmed' if year_match else 'suspected'
                elif score >= 0.50:
                    status = 'suspected'
                else:
                    status = 'unmatched'

                best_match = {
                    'match_status': status,
                    'match_score': round(score, 3),
                    'organization': org,
                    'person': person,
                    'match_notes': f'Club coincide ({org.name}). {notes}'.strip(),
                }

    # Si ya se confirmó o sospechó con club coincidente, retornar
    if best_match['match_status'] in ['confirmed', 'suspected']:
        return best_match

    # 2. Si no hay coincidencia con club, buscar en todas las organizaciones para detectar homónimos o cesiones
    for org in all_orgs:
        if org in matched_orgs:
            continue
        candidates = list(
            Person.objects.filter(
                organization=org,
                player_roles__season=season,
                player_roles__is_active=True,
            ).distinct()
        )
        for person in candidates:
            score, year_match, notes = evaluate_person(person)
            # Solo sospechamos si la coincidencia es altísima y el año coincide
            if score >= 0.95 and year_match and score > best_match['match_score']:
                best_match = {
                    'match_status': 'suspected',
                    'match_score': round(score, 3),
                    'organization': org,
                    'person': person,
                    'match_notes': f'Coincidencia casi exacta con {org.name} pero club en PDF es "{raw_club}". Posible cesión o filial.',
                }

    return best_match
