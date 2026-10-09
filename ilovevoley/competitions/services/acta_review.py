"""Servicio de validación, comparación con plantilla y revisión de actas manuales.

Proporciona la lógica de negocio para la revisión en el admin:
- Validación de datos extraídos (dorsales 0-99 sin duplicados, compatibilidad de equipos, avisos de parciales y sanciones).
- Comparación de convocados del acta con la plantilla oficial registrada (PlayerRole).
- Aprobación (approve_acta_photo) y rechazo (reject_acta_photo) de registros MatchActaPhoto.
"""

import logging
import re
from typing import Optional, Tuple

from django.db import transaction
from django.utils import timezone
from unidecode import unidecode

from ilovevoley.competitions.models import Match, MatchActaPhoto
from ilovevoley.competitions.services.lineups import (
    _roles_lookup,
    resolve_acta_team,
    store_match_lineups,
)
from ilovevoley.videos.scraping.base import is_penalty_result

logger = logging.getLogger(__name__)


def _names_match(name_acta: str, last_name: str, first_name: str = '') -> bool:
    """Comprueba si el nombre leído en el acta coincide parcialmente con el de la plantilla."""
    if not name_acta:
        return True
    w_acta = set(unidecode(name_acta).upper().split())
    w_last = set(unidecode(last_name or '').upper().split())
    w_first = set(unidecode(first_name or '').upper().split())
    return bool(w_acta & (w_last | w_first))


def validate_acta_data(match: Match, data: dict) -> Tuple[bool, list[str], list[str]]:
    """
    Valida las reglas de negocio de los datos del acta manual.

    Retorna (is_valid, errors, warnings) donde:
    - errors: errores bloqueantes (dorsales fuera de 0-99, duplicados, equipos incompatibles).
    - warnings: avisos no bloqueantes (parciales no coincidentes con federación, partidos sancionados).
    """
    errors = []
    warnings = []

    if not isinstance(data, dict):
        return False, ['Los datos del acta deben ser un objeto JSON válido.'], []

    home_team = match.home_team
    away_team = match.away_team

    # 1. Validar convocados y dorsales (enteros 0-99 sin repetir por equipo)
    for team_label, key, team in (
        ('local', 'home_convocados', home_team),
        ('visitante', 'away_convocados', away_team),
    ):
        team_display = team.name if team else team_label.capitalize()
        convocados = data.get(key) or []
        if not isinstance(convocados, list):
            errors.append(f'La lista de convocados del equipo {team_display} no es válida.')
            continue

        seen_jerseys = set()
        for idx, entry in enumerate(convocados, 1):
            entry_str = str(entry).strip()
            matched = re.match(r'^(\d+)(?:\s+(.*))?$', entry_str)
            if not matched:
                errors.append(
                    f"Convocado #{idx} en equipo {team_display} ('{entry_str}') no tiene un dorsal numérico válido."
                )
                continue

            jersey = int(matched.group(1))
            if jersey < 0 or jersey > 99:
                errors.append(
                    f'Dorsal {jersey} en equipo {team_display} está fuera del rango permitido (0-99).'
                )

            if jersey in seen_jerseys:
                errors.append(
                    f'Dorsal {jersey} duplicado en el equipo {team_display}.'
                )
            seen_jerseys.add(jersey)

    # 2. Validar que los equipos concuerdan con el partido si se especifican
    acta_home_name = data.get('home_team')
    acta_away_name = data.get('away_team')
    if acta_home_name and acta_away_name and home_team and away_team:
        resolved_home = resolve_acta_team(acta_home_name, home_team, away_team)
        resolved_away = resolve_acta_team(acta_away_name, home_team, away_team)
        if resolved_home == away_team and resolved_away == home_team:
            errors.append(
                f"Los equipos leídos ('{acta_home_name}' vs '{acta_away_name}') están invertidos respecto al local y visitante del partido."
            )

    # 3. Validar parciales leídos contra los oficiales de la federación (no bloqueante)
    data_sets = data.get('sets') or []
    if match.set_scores and isinstance(data_sets, list) and data_sets:
        official_sets = [tuple(score) for score in match.set_scores]
        read_sets = []
        for s in data_sets:
            if isinstance(s, dict) and 'home_points' in s and 'away_points' in s:
                try:
                    read_sets.append((int(s['home_points']), int(s['away_points'])))
                except (ValueError, TypeError):
                    pass

        if read_sets and read_sets != official_sets:
            official_str = '/'.join(f'{h}-{a}' for h, a in official_sets)
            read_str = '/'.join(f'{h}-{a}' for h, a in read_sets)
            warnings.append(
                f'Los parciales leídos ({read_str}) no coinciden con los oficiales ({official_str}). Prevalecen los oficiales.'
            )

    # 4. Comprobar si es un resultado sancionado por resolución federativa (no bloqueante)
    if match.result_penalized or is_penalty_result(match.set_scores):
        warnings.append(
            'El partido tiene un resultado sancionado por resolución federativa. Revisar observaciones del acta.'
        )

    # 5. Comprobar sets ganados contra tanteo del partido (no bloqueante)
    if match.home_score is not None and match.away_score is not None and data_sets:
        home_sets_won = 0
        away_sets_won = 0
        for s in data_sets:
            if isinstance(s, dict):
                hp = s.get('home_points') or 0
                ap = s.get('away_points') or 0
                if hp > ap:
                    home_sets_won += 1
                elif ap > hp:
                    away_sets_won += 1
        if (home_sets_won or away_sets_won) and (home_sets_won, away_sets_won) != (match.home_score, match.away_score):
            warnings.append(
                f'Los sets ganados en el acta ({home_sets_won}-{away_sets_won}) difieren del resultado oficial ({match.home_score}-{match.away_score}).'
            )

    is_valid = len(errors) == 0
    return is_valid, errors, warnings


def get_acta_roster_comparison(match: Match, data: dict) -> dict:
    """
    Compara los convocados del acta con la plantilla oficial (PlayerRole) para local y visitante.

    Devuelve un diccionario estructurado para que el admin pueda mostrar:
    dorsal · nombre leído · nombre en plantilla · coincide.
    """
    from ilovevoley.core.models import Organization
    from ilovevoley.teams.models import Team

    active_orgs = Organization.objects.filter(is_active=True)
    roles_lookup = _roles_lookup(match)

    def _is_tenant_team(team):
        if not team:
            return False
        return any(Team.objects.for_tenant(org).filter(pk=team.pk).exists() for org in active_orgs)

    comparison = {}

    for side, team in (('home', match.home_team), ('away', match.away_team)):
        is_tenant = _is_tenant_team(team)
        convocados = data.get(f'{side}_convocados') or []
        players = []
        seen_jerseys = set()

        for entry in convocados:
            matched = re.match(r'^(\d+)(?:\s+(.*))?$', str(entry or '').strip())
            if matched:
                jersey = int(matched.group(1))
                name_acta = (matched.group(2) or '').strip()
                seen_jerseys.add(jersey)

                role = roles_lookup.get((team.id, jersey)) if team else None
                if role and role.person:
                    p = role.person
                    roster_name = p.last_name or p.first_name
                    matches = _names_match(name_acta, p.last_name, p.first_name)
                    person_id = p.id
                    is_in_roster = True
                else:
                    roster_name = ''
                    matches = None if not is_tenant else False
                    person_id = None
                    is_in_roster = False

                players.append({
                    'jersey_number': jersey,
                    'name_acta': name_acta,
                    'roster_name': roster_name,
                    'person_id': person_id,
                    'is_in_roster': is_in_roster,
                    'matches': matches,
                })
            else:
                players.append({
                    'jersey_number': None,
                    'name_acta': str(entry or '').strip(),
                    'roster_name': '',
                    'person_id': None,
                    'is_in_roster': False,
                    'matches': False,
                })

        missing_from_acta = []
        if team:
            for (t_id, num), role in roles_lookup.items():
                if t_id == team.id and num not in seen_jerseys:
                    p = role.person
                    missing_from_acta.append({
                        'jersey_number': num,
                        'roster_name': p.last_name or p.first_name if p else '',
                        'person_id': p.id if p else None,
                    })

        missing_from_acta.sort(key=lambda x: x['jersey_number'] or 0)

        comparison[side] = {
            'team_name': team.name if team else getattr(match, f'{side}_team_display', ''),
            'is_tenant': is_tenant,
            'players': players,
            'missing_from_acta': missing_from_acta,
        }

    return comparison


@transaction.atomic
def approve_acta_photo(
    photo: MatchActaPhoto,
    data: Optional[dict] = None,
    user=None,
) -> Tuple[bool, list[str]]:
    """
    Valida y aprueba el acta manual.

    Si los datos son válidos:
    - Ejecuta store_match_lineups(photo.match, data).
    - Actualiza photo a 'approved', registrando reviewed_by, reviewed_at y warnings.
    - Retorna (True, warnings).

    Si los datos son inválidos:
    - No modifica MatchLineup ni el partido.
    - Guarda los errores en photo.validation_errors.
    - Retorna (False, errors).
    """
    target_data = data if data is not None else (photo.extracted_data or {})
    is_valid, errors, warnings = validate_acta_data(photo.match, target_data)

    if not is_valid:
        photo.validation_errors = errors
        photo.save(update_fields=['validation_errors', 'updated_at'])
        return False, errors

    store_match_lineups(photo.match, target_data)

    photo.extracted_data = target_data
    photo.status = 'approved'
    photo.reviewed_by = user
    photo.reviewed_at = timezone.now()
    photo.validation_errors = warnings
    photo.save(update_fields=[
        'extracted_data',
        'status',
        'reviewed_by',
        'reviewed_at',
        'validation_errors',
        'updated_at',
    ])

    return True, warnings


def reject_acta_photo(
    photo: MatchActaPhoto,
    user=None,
    reason: str = '',
) -> bool:
    """
    Rechaza el acta manual y registra revisor y motivo opcional.
    """
    photo.status = 'rejected'
    photo.reviewed_by = user
    photo.reviewed_at = timezone.now()
    if reason:
        if not isinstance(photo.extraction_meta, dict):
            photo.extraction_meta = {}
        photo.extraction_meta['reject_reason'] = reason
    photo.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'extraction_meta', 'updated_at'])
    return True


__all__ = [
    'approve_acta_photo',
    'get_acta_roster_comparison',
    'reject_acta_photo',
    'validate_acta_data',
]
