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


def _club_has_gender(org: Organization, gender: str) -> bool:
    """Comprueba si el club de la organización tiene equipos del género de la convocatoria."""
    if not gender or gender not in ['M', 'F']:
        return True

    from ilovevoley.teams.models import Team
    teams = Team.objects.filter(club=org.club) if hasattr(org, 'club') and org.club else Team.objects.none()
    if not teams.exists():
        teams = Team.objects.filter(player_roles__person__organization=org)

    if not teams.exists():
        return False

    female_kws = ['FEM', 'FEMENI', 'FEMENINA', 'FEMENINO']
    male_kws = ['MASC', 'MASCULI', 'MASCULINA', 'MASCULINO']

    has_female = False
    has_male = False
    for t in teams.distinct():
        t_str = f"{t.name} {t.category.name if t.category else ''}".upper()
        if any(kw in t_str for kw in female_kws):
            has_female = True
        if any(kw in t_str for kw in male_kws):
            has_male = True

    if gender == 'F':
        return has_female or (not has_male)
    elif gender == 'M':
        return has_male or (not has_female)
    return True


# Variantes catalán / castellano y apodos comunes en Baleares / España
NAME_VARIANTS: dict[str, set[str]] = {
    'JOAN': {'JUAN'},
    'JUAN': {'JOAN'},
    'JOSEP': {'JOSE', 'PEP', 'PEPE'},
    'JOSE': {'JOSEP', 'PEP', 'PEPE'},
    'PEP': {'JOSEP', 'JOSE', 'PEPE'},
    'PEPE': {'JOSEP', 'JOSE', 'PEP'},
    'FRANCISCO': {'XISCO', 'FRANCESC', 'CISCO', 'PACO', 'CURRO'},
    'XISCO': {'FRANCISCO', 'FRANCESC', 'CISCO', 'PACO'},
    'FRANCESC': {'FRANCISCO', 'XISCO'},
    'JAVIER': {'JAVI'},
    'JAVI': {'JAVIER'},
    'ANTONIO': {'TONI', 'ANTONI'},
    'ANTONI': {'TONI', 'ANTONIO'},
    'TONI': {'ANTONIO', 'ANTONI'},
    'DANIEL': {'DANI'},
    'DANI': {'DANIEL'},
    'ALEJANDRO': {'ALEX', 'ALEIX'},
    'ALEX': {'ALEJANDRO', 'ALEIX'},
    'ALEIX': {'ALEJANDRO', 'ALEX'},
    'GABRIEL': {'BIEL'},
    'BIEL': {'GABRIEL'},
    'JAIME': {'JAUME'},
    'JAUME': {'JAIME'},
    'MIGUEL': {'MIQUEL'},
    'MIQUEL': {'MIGUEL'},
    'SEBASTIAN': {'SEBASTIA', 'SEBAS'},
    'SEBASTIA': {'SEBASTIAN', 'SEBAS'},
    'SEBAS': {'SEBASTIAN', 'SEBASTIA'},
    'BERNARDO': {'BERNAT'},
    'BERNAT': {'BERNARDO'},
    'GUILLERMO': {'GUILLEM', 'GUILLE'},
    'GUILLEM': {'GUILLERMO', 'GUILLE'},
    'PABLO': {'PAU'},
    'PAU': {'PABLO'},
    'LUIS': {'LLUIS'},
    'LLUIS': {'LUIS'},
    'IGNACIO': {'NACHO', 'IGNASI'},
    'IGNASI': {'IGNACIO', 'NACHO'},
    'NACHO': {'IGNACIO', 'IGNASI'},
    'RAFAEL': {'RAFA'},
    'RAFA': {'RAFAEL'},
    'CARLOS': {'CARLES'},
    'CARLES': {'CARLOS'},
    'VICENTE': {'VICENC', 'VICENT'},
    'VICENC': {'VICENTE', 'VICENT'},
    'VICENT': {'VICENTE', 'VICENC'},
    'ANDRES': {'ANDREU'},
    'ANDREU': {'ANDRES'},
    'JORGE': {'JORDI'},
    'JORDI': {'JORGE'},
    'ESTEBAN': {'ESTEVE'},
    'ESTEVE': {'ESTEBAN'},
    'MATEO': {'MATEU'},
    'MATEU': {'MATEO'},
    'BARTOLOME': {'BARTOMEU', 'TOMEU'},
    'BARTOMEU': {'BARTOLOME', 'TOMEU'},
    'TOMEU': {'BARTOLOME', 'BARTOMEU'},
    'ENRIQUE': {'QUIQUE'},
    'QUIQUE': {'ENRIQUE'},
    'MANUEL': {'MANOLO', 'MANU'},
    'MANOLO': {'MANUEL'},
    'MANU': {'MANUEL'},
    'ALBERTO': {'BERTO'},
}


def _first_names_match(raw_first: str, p_first: str) -> float:
    raw_tokens = _tokenize(raw_first)
    p_tokens = _tokenize(p_first)
    if not raw_tokens or not p_tokens:
        return 0.0

    r0, p0 = raw_tokens[0], p_tokens[0]
    # Coincidencia exacta del primer token
    if r0 == p0:
        return 1.0

    # Coincidencia por variante catalán/castellano o apodo
    if p0 in NAME_VARIANTS.get(r0, set()) or r0 in NAME_VARIANTS.get(p0, set()):
        return 1.0

    # Subconjunto de tokens de nombre (ej. Juan Carlos vs Juan)
    if set(raw_tokens).issubset(set(p_tokens)) or set(p_tokens).issubset(set(raw_tokens)):
        return 1.0

    # Errata tipográfica menor en el nombre (ratio >= 0.85 para 4+ letras)
    if len(r0) >= 4 and len(p0) >= 4:
        ratio = SequenceMatcher(None, r0, p0).ratio()
        if ratio >= 0.85:
            return 0.85

    return 0.0


def _last_names_match(raw_last: str, p_last: str) -> float:
    raw_tokens = _tokenize(raw_last)
    p_tokens = _tokenize(p_last)
    if not raw_tokens or not p_tokens:
        return 0.0

    # Coincidencia exacta de todos los apellidos
    if raw_tokens == p_tokens:
        return 1.0

    # Primer apellido coincide exactamente (ej: 'ROCA' en 'ROCA PUJOL', o al revés)
    if raw_tokens[0] == p_tokens[0]:
        return 0.95

    # Subconjunto de apellidos (el apellido de la BD está en los del PDF o viceversa)
    if set(p_tokens).issubset(set(raw_tokens)) or set(raw_tokens).issubset(set(p_tokens)):
        return 0.95

    # Errata tipográfica en el primer apellido (ratio >= 0.85 y 4+ letras)
    if len(raw_tokens[0]) >= 4 and len(p_tokens[0]) >= 4:
        ratio = SequenceMatcher(None, raw_tokens[0], p_tokens[0]).ratio()
        if ratio >= 0.85:
            return 0.85

    return 0.0


def match_callup_player(
    player_data: dict[str, Any],
    season: Season,
    callup: Any | None = None,
) -> dict[str, Any]:
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

    def evaluate_person(person: Person) -> tuple[float, bool, str]:
        # Si la convocatoria tiene género 'M' o 'F', comprobar que no haya conflicto con los equipos del jugador
        if callup and getattr(callup, 'gender', None) in ['M', 'F']:
            c_gender = callup.gender
            player_teams = [r.team for r in person.player_roles.filter(season=season)]
            has_gender_conflict = False
            for t in player_teams:
                t_str = f"{t.name} {t.category.name if t.category else ''}".upper()
                if c_gender == 'M' and any(w in t_str for w in ['FEM', 'FEMENI', 'FEMENINA', 'FEMENINO']):
                    has_gender_conflict = True
                elif c_gender == 'F' and any(w in t_str for w in ['MASC', 'MASCULI', 'MASCULINA', 'MASCULINO']):
                    has_gender_conflict = True
            if has_gender_conflict:
                return 0.0, False, f'Conflicto de género: convocatoria {c_gender} vs equipo del jugador'

        first_score = _first_names_match(raw_first, person.first_name)
        last_score = _last_names_match(raw_last, person.last_name)

        # REGLA ESTRICTA: Si no coincide el nombre O no coincide ningún apellido, score = 0.0
        # Evita por completo que SequenceMatcher otorgue 0.30 por vocales sueltas
        if first_score == 0.0 or last_score == 0.0:
            return 0.0, False, 'Sin coincidencia suficiente en nombre o apellidos'

        base_score = (first_score * 0.40) + (last_score * 0.60)

        # Validación de año de nacimiento
        year_match = False
        notes = []
        if raw_year and person.birth_date:
            if raw_year == person.birth_date.year:
                year_match = True
                notes.append(f'Año {raw_year} confirmado')
            elif abs(raw_year - person.birth_date.year) > 1:
                base_score = max(0.0, base_score - 0.25)
                notes.append(f'Descuadre año: PDF {raw_year} vs ficha {person.birth_date.year}')

        note_str = '; '.join(notes)
        return base_score, year_match, note_str

    # 1. Búsqueda en organizaciones donde el club coincide
    valid_matched_orgs = []
    c_gender = getattr(callup, 'gender', None) if callup else None
    for org in matched_orgs:
        if c_gender and not _club_has_gender(org, c_gender):
            continue
        valid_matched_orgs.append(org)

    best_candidate_match = None
    best_score = 0.0

    for org in valid_matched_orgs:
        candidates = list(
            Person.objects.filter(
                organization=org,
                player_roles__season=season,
                player_roles__is_active=True,
            ).distinct()
        )
        if not candidates:
            candidates = list(Person.objects.filter(organization=org))

        for person in candidates:
            score, year_match, notes = evaluate_person(person)
            if score > best_score:
                best_score = score
                best_candidate_match = {
                    'person': person,
                    'organization': org,
                    'score': score,
                    'year_match': year_match,
                    'notes': notes,
                }

    # Si encontramos un candidato con puntuación suficiente en las organizaciones coincidentes:
    if best_candidate_match:
        cand_score = best_candidate_match['score']
        cand_person = best_candidate_match['person']
        cand_org = best_candidate_match['organization']
        cand_notes = best_candidate_match['notes']
        cand_year_match = best_candidate_match['year_match']

        if cand_score >= 0.85:
            return {
                'match_status': 'confirmed',
                'match_score': round(cand_score, 3),
                'organization': cand_org,
                'person': cand_person,
                'match_notes': f'Club coincide ({cand_org.name}). {cand_notes}'.strip(),
            }
        elif cand_score >= 0.70 or (cand_score >= 0.65 and cand_year_match):
            return {
                'match_status': 'confirmed' if (cand_year_match and cand_score >= 0.75) else 'suspected',
                'match_score': round(cand_score, 3),
                'organization': cand_org,
                'person': cand_person,
                'match_notes': f'Club coincide ({cand_org.name}). {cand_notes}'.strip(),
            }

    # Si el club coincide pero ningún jugador supera el umbral (0 matching o ficha inexistente en la app)
    # Marcar como 'suspected' sin ficha asignada (person=None) para alertar a los managers del club
    if valid_matched_orgs:
        primary_org = valid_matched_orgs[0]
        return {
            'match_status': 'suspected',
            'match_score': 0.0,
            'organization': primary_org,
            'person': None,
            'match_notes': f'Club coincide ({primary_org.name}), pero el jugador no tiene ficha creada en la app.',
        }

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
            if score >= 0.95 and year_match:
                return {
                    'match_status': 'suspected',
                    'match_score': round(score, 3),
                    'organization': org,
                    'person': person,
                    'match_notes': f'Coincidencia casi exacta con {org.name} pero club en PDF es "{raw_club}". Posible cesión o filial.',
                }

    return {
        'match_status': 'unmatched',
        'match_score': 0.0,
        'organization': None,
        'person': None,
        'match_notes': '',
    }
