"""Servicio de transcripción de actas manuales con Gemini Vision (REST).

Realiza la lectura de la imagen del acta mediante la API REST de Google Gemini
(gemini-3.5-flash-lite) con prompt contextualizado (equipos y plantilla conocida),
normalizando la respuesta al esquema de parse_acta_lineup para su posterior revisión.
"""

import base64
import json
import logging
import os
from typing import Optional

from django.conf import settings
import requests

from ilovevoley.competitions.models import Match, MatchActaPhoto
from ilovevoley.competitions.services.acta_photo import download_and_prepare_acta_photo

logger = logging.getLogger(__name__)

DEFAULT_GEMINI_MODEL = 'gemini-3.5-flash-lite'


class ActaVisionError(Exception):
    """Error base al procesar el acta con Gemini Vision."""


class ActaVisionTransientError(ActaVisionError):
    """Error transitorio de red o servicio (429, 503, timeout); se debe reintentar."""


class ActaVisionBrokenJsonError(ActaVisionError):
    """El modelo devolvió una respuesta que no es JSON válido."""


def build_acta_context(match: Match) -> dict:
    """
    Construye el contexto del partido para el prompt de visión.

    Incluye nombres de los equipos y la plantilla conocida (dorsal -> apellido)
    del equipo perteneciente a un tenant activo para minimizar alucinaciones.
    """
    from ilovevoley.core.models import Organization
    from ilovevoley.rosters.models import PlayerRole
    from ilovevoley.teams.models import Team

    context = {
        'home_team': match.home_team_display,
        'away_team': match.away_team_display,
        'match_date': match.match_date.strftime('%d/%m/%Y') if match.match_date else '',
        'tenant_roster': [],
        'tenant_team_name': '',
        'is_home_tenant': False,
        'is_away_tenant': False,
    }

    active_orgs = Organization.objects.filter(is_active=True)
    tenant_team = None

    for org in active_orgs:
        tenant_teams = Team.objects.for_tenant(org)
        if match.home_team and tenant_teams.filter(pk=match.home_team.pk).exists():
            tenant_team = match.home_team
            context['is_home_tenant'] = True
            break
        elif match.away_team and tenant_teams.filter(pk=match.away_team.pk).exists():
            tenant_team = match.away_team
            context['is_away_tenant'] = True
            break

    if tenant_team and tenant_team.identity_id:
        context['tenant_team_name'] = tenant_team.name
        season = match.league.season if match.league_id else None
        roles = PlayerRole.objects.filter(
            identity_id=tenant_team.identity_id,
            jersey_number__isnull=False,
        ).select_related('person')
        if season is not None:
            roles = roles.filter(season=season)
        roles = roles.order_by('jersey_number', 'id')

        roster_list = []
        for r in roles:
            p_name = r.person.last_name if r.person and r.person.last_name else ''
            if not p_name and r.person:
                p_name = r.person.first_name
            roster_list.append((r.jersey_number, p_name))
        context['tenant_roster'] = roster_list

    return context


def build_acta_prompt(context: dict) -> str:
    """Genera el texto de instrucción para el modelo de visión."""
    home = context.get('home_team', '')
    away = context.get('away_team', '')
    roster = context.get('tenant_roster') or []
    tenant_name = context.get('tenant_team_name', '')

    roster_lines = ''
    if roster and tenant_name:
        roster_str = ', '.join(f'{num} {name}'.strip() for num, name in roster)
        roster_lines = (
            f'\nPlantilla oficial conocida para {tenant_name} (dorsal y apellido): {roster_str}.\n'
            'Para este equipo, utiliza la lista para confirmar o corregir la transcripción de nombres. '
            'NO inventes jugadores ni cambies dorsales que aparezcan claramente en el acta física.\n'
        )

    return (
        'Eres un transcriptor experto de actas oficiales de partidos de voleibol. '
        'La imagen adjunta es la foto de un acta (en papel o captura de aplicación) y puede estar girada.\n'
        f'Contexto del partido: local = "{home}", visitante = "{away}".\n'
        f'{roster_lines}'
        'Transcribe EXACTAMENTE lo que ves. Lo que no se lea con claridad déjalo como \'\' o vacía la lista. '
        'NO inventes información no visible.\n'
        'Los nombres de los equipos corresponden a las secciones EQUIPO LOCAL y EQUIPO VISITANTE, no a la cancha ni la sede.\n'
        'Devuelve ÚNICAMENTE un objeto JSON con la siguiente estructura exacta:\n'
        '{\n'
        '  "rotation_degrees_needed": 0,\n'
        '  "format": "paper_alevin|app_screenshot|paper_full|other",\n'
        '  "confidence": "high|medium|low",\n'
        '  "home_team": "",\n'
        '  "away_team": "",\n'
        '  "home_captain": "",\n'
        '  "away_captain": "",\n'
        '  "home_coach": "",\n'
        '  "away_coach": "",\n'
        '  "home_convocados": ["<dorsal> <apellido>"],\n'
        '  "away_convocados": ["<dorsal> <apellido>"],\n'
        '  "sets": [\n'
        '    {"title": "Set 1", "home_points": 0, "away_points": 0}\n'
        '  ],\n'
        '  "observations": "",\n'
        '  "referees": [],\n'
        '  "officials": []\n'
        '}'
    )


def parse_acta_vision_result(data: dict, context: Optional[dict] = None) -> dict:
    """
    Normaliza el JSON devuelto por Gemini al esquema canónico de parse_acta_lineup.

    Los metadatos adicionales de la transcripción se adjuntan en la clave '_meta'.
    """
    context = context or {}
    home_team = (data.get('home_team') or '').strip() or context.get('home_team', '')
    away_team = (data.get('away_team') or '').strip() or context.get('away_team', '')

    def _clean_convocados(raw_list):
        if not raw_list or not isinstance(raw_list, list):
            return []
        cleaned = []
        for item in raw_list:
            if isinstance(item, dict):
                num = item.get('number') or item.get('dorsal', '')
                name = item.get('name') or item.get('apellido', '')
                cleaned.append(f'{num} {name}'.strip())
            elif isinstance(item, str):
                cleaned.append(item.strip())
            elif isinstance(item, (int, float)):
                cleaned.append(str(int(item)))
        return [c for c in cleaned if c]

    home_convocados = _clean_convocados(data.get('home_convocados'))
    away_convocados = _clean_convocados(data.get('away_convocados'))

    sets_raw = data.get('sets') or []
    sets = []
    if isinstance(sets_raw, list):
        for idx, s in enumerate(sets_raw, 1):
            if isinstance(s, dict):
                set_dict = dict(s)
                if 'title' not in set_dict:
                    set_dict['title'] = f'Set {idx}'
                sets.append(set_dict)

    referees_raw = data.get('referees') or []
    referees = [str(r).strip() for r in referees_raw if r] if isinstance(referees_raw, list) else []

    officials_raw = data.get('officials') or []
    officials = [o for o in officials_raw if isinstance(o, dict)] if isinstance(officials_raw, list) else []

    result = {
        'home_team': home_team,
        'away_team': away_team,
        'home_captain': (data.get('home_captain') or '').strip(),
        'away_captain': (data.get('away_captain') or '').strip(),
        'home_convocados': home_convocados,
        'away_convocados': away_convocados,
        'sets': sets,
        'observations': (data.get('observations') or '').strip(),
        'home_coach': (data.get('home_coach') or '').strip(),
        'away_coach': (data.get('away_coach') or '').strip(),
        'referees': referees,
        'officials': officials,
    }

    result['_meta'] = {
        'rotation_degrees_needed': data.get('rotation_degrees_needed', 0),
        'format': data.get('format', 'other'),
        'confidence': data.get('confidence', ''),
        'notes': data.get('notes', ''),
    }

    return result


def read_acta(
    image_bytes: bytes,
    context: dict,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    timeout: int = 60,
) -> dict:
    """
    Envía la foto del acta al modelo Gemini Vision mediante llamada REST directa.

    Devuelve un diccionario conforme al esquema de parse_acta_lineup con los metadatos
    de extracción en la clave '_meta'.
    """
    key = api_key or getattr(settings, 'GEMINI_API_KEY', '') or os.environ.get('GEMINI_API_KEY', '')
    if not key:
        raise ValueError('GEMINI_API_KEY no está configurada')

    selected_model = model or getattr(settings, 'GEMINI_ACTA_MODEL', DEFAULT_GEMINI_MODEL)
    prompt = build_acta_prompt(context)

    url = f'https://generativelanguage.googleapis.com/v1beta/models/{selected_model}:generateContent'
    headers = {
        'x-goog-api-key': key,
        'Content-Type': 'application/json',
    }
    payload = {
        'contents': [
            {
                'parts': [
                    {'text': prompt},
                    {
                        'inline_data': {
                            'mime_type': 'image/jpeg',
                            'data': base64.b64encode(image_bytes).decode('ascii'),
                        }
                    },
                ]
            }
        ],
        'generationConfig': {
            'responseMimeType': 'application/json',
            'temperature': 0,
        },
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.exceptions.Timeout as e:
        raise ActaVisionTransientError(f'Timeout conectando con Gemini API: {e}')
    except requests.exceptions.RequestException as e:
        raise ActaVisionTransientError(f'Error de red conectando con Gemini API: {e}')

    if response.status_code in (429, 503):
        raise ActaVisionTransientError(
            f'Gemini API rate limit o sobrecarga HTTP {response.status_code}: {response.text}'
        )
    elif response.status_code != 200:
        raise ActaVisionError(f'Gemini API error HTTP {response.status_code}: {response.text}')

    try:
        data = response.json()
    except Exception as e:
        raise ActaVisionError(f'Respuesta de Gemini API no es JSON: {e}')

    if 'error' in data:
        code = data['error'].get('code')
        msg = data['error'].get('message', '')
        if code in (429, 503):
            raise ActaVisionTransientError(f'Gemini API error {code}: {msg}')
        raise ActaVisionError(f'Gemini API error {code}: {msg}')

    try:
        candidate = data['candidates'][0]
        raw_text = candidate['content']['parts'][0]['text']
    except (KeyError, IndexError) as e:
        raise ActaVisionError(f'Estructura inesperada en respuesta de Gemini: {e}')

    try:
        parsed_json = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ActaVisionBrokenJsonError(f'JSON inválido devuelto por el modelo: {e}')

    result = parse_acta_vision_result(parsed_json, context=context)
    if 'usageMetadata' in data:
        result['_meta']['usage'] = data['usageMetadata']

    return result


def process_acta_photo_batch(limit: int = 5) -> int:
    """
    Procesa un lote de MatchActaPhoto pendientes de descarga o lectura.

    1. Descarga y normaliza imagen para registros en 'pending_download'.
    2. Si ACTA_VISION_ENABLED está activo, transcribe las fotos pendientes de leer.
    3. Errores transitorios (429/503) dejan la foto en 'pending_read' para el siguiente ciclo.
    """
    vision_enabled = getattr(settings, 'ACTA_VISION_ENABLED', False)
    api_key = getattr(settings, 'GEMINI_API_KEY', '') or os.environ.get('GEMINI_API_KEY', '')

    pending_qs = (
        MatchActaPhoto.objects.filter(
            status__in=['pending_download', 'downloaded', 'pending_read']
        )
        .select_related(
            'match',
            'match__home_team',
            'match__away_team',
            'match__league',
            'match__league__season',
        )
        .order_by('id')[:limit]
    )

    processed_count = 0

    for photo in pending_qs:
        # 1. Si no tiene imagen o está en pending_download, descargar primero
        if photo.status == 'pending_download' or not photo.image:
            ok = download_and_prepare_acta_photo(photo)
            if not ok:
                continue
            photo.refresh_from_db()

        # Si la visión no está habilitada o no hay clave, la foto queda descargada y lista
        if not vision_enabled or not api_key:
            continue

        # 2. Transcripción con Gemini Vision
        context = build_acta_context(photo.match)
        try:
            with photo.image.open('rb') as img_f:
                image_bytes = img_f.read()
            parsed = read_acta(image_bytes, context, api_key=api_key)
        except ActaVisionTransientError as e:
            logger.warning(f'Error transitorio de Gemini Vision en acta {photo.id}: {e}')
            photo.status = 'pending_read'
            photo.save(update_fields=['status', 'updated_at'])
            # Ante saturación de API, detenemos el lote actual para esperar a la siguiente ejecución
            break
        except ActaVisionBrokenJsonError as e:
            logger.warning(f'JSON roto de Gemini Vision en acta {photo.id}: {e}')
            photo.status = 'pending_review'
            photo.extraction_meta = {'error': str(e)}
            photo.save(update_fields=['status', 'extraction_meta', 'updated_at'])
            processed_count += 1
        except Exception as e:
            logger.warning(f'Error inesperado procesando acta con visión {photo.id}: {e}')
            photo.status = 'pending_review'
            photo.extraction_meta = {'error': str(e)}
            photo.save(update_fields=['status', 'extraction_meta', 'updated_at'])
            processed_count += 1
        else:
            meta = parsed.pop('_meta', {})
            photo.extracted_data = parsed
            photo.extraction_meta = meta
            photo.status = 'pending_review'
            photo.save(update_fields=['extracted_data', 'extraction_meta', 'status', 'updated_at'])
            processed_count += 1

    return processed_count


__all__ = [
    'ActaVisionBrokenJsonError',
    'ActaVisionError',
    'ActaVisionTransientError',
    'build_acta_context',
    'build_acta_prompt',
    'parse_acta_vision_result',
    'process_acta_photo_batch',
    'read_acta',
]
