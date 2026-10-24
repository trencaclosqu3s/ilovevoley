"""Motor de redacción con LLM (#551): hechos ya calculados → texto natural.

El modelo no calcula ni decide: recibe un dict de hechos seudonimizados y devuelve
un texto con el marcador ``{nombre}``, que se sustituye aquí al renderizar (D1). El
motor no conoce el dominio (voleibol, wrapped, cromo): cada llamador construye sus
hechos y fija su límite de longitud. Solo se llama desde tareas Celery.
"""

import json
import logging
import re
import time

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

NAME_MARKER = '{nombre}'
TRANSIENT_HTTP_CODES = (429, 500, 502, 503, 504)
# Claves de los hechos cuyos números no son cifras que el modelo pueda citar.
_NON_FIGURE_KEYS = ('temporada', 'max_caracteres')
_last_call = 0.0
_LANGUAGE_NAMES = {'es': 'castellano', 'ca': 'catalán'}
CACHE_KEY_LAST_CALL = 'core:narrative:last_call'
CACHE_KEY_LOCK = 'core:narrative:lock'
_LOCK_TIMEOUT = 10.0
_LOCK_RETRY_DELAY = 0.05
_STYLE_HEADERS = {
    'wrapped': (
        'Redacta un párrafo breve para el resumen de temporada de una persona que juega a '
        'voleibol, en tercera persona, para que lo lean ella y su familia.'
    ),
    'card': (
        'Redacta una frase corta para el cromo de una jugadora o jugador de voleibol, en '
        'tercera persona, pensada para compartirse.'
    ),
}


class NarrativeError(Exception):
    """Fallo no recuperable de la API (HTTP inesperado, respuesta con otra estructura)."""


class NarrativeTransientError(NarrativeError):
    """Red, timeout, 429 o 5xx: se reintenta la noche siguiente."""


class NarrativeDiscarded(NarrativeError):
    """El modelo respondió, pero el texto no supera la validación: no se reintenta (D2)."""


def is_enabled() -> bool:
    return bool(settings.LLM_NARRATIVE_ENABLED and settings.LLM_NARRATIVE_API_KEY)


def fill_name(text: str, name: str) -> str:
    """Sustituye ``{nombre}`` por el nombre real. Único punto de sustitución (D1)."""
    return text.replace(NAME_MARKER, name)


def redact(facts: dict, *, locale: str, max_chars: int, style: str) -> str | None:
    """Texto validado (con ``{nombre}``) o ``None`` si la capa está apagada.

    Lanza ``NarrativeTransientError`` (reintentar) o ``NarrativeDiscarded`` (no reintentar).
    """
    if not is_enabled():
        return None
    payload = {**facts, 'idioma': locale, 'max_caracteres': max_chars}
    raw = _post_to_provider(_build_prompt(payload, style))
    try:
        text = json.loads(raw)['text']
    except (ValueError, KeyError, TypeError) as e:
        raise NarrativeDiscarded(f'El modelo no devolvió {{"text": ...}}: {e}')
    return _validate(text, payload, max_chars)


def _build_prompt(payload: dict, style: str) -> str:
    language = _LANGUAGE_NAMES.get(payload['idioma'], payload['idioma'])
    return '\n'.join([
        _STYLE_HEADERS[style],
        '',
        'HECHOS (JSON):',
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        '',
        'REGLAS:',
        f'1. Escribe en {language}, sin mezclar idiomas.',
        '2. Usa solo los números del bloque HECHOS, cada uno con su propia etiqueta '
        '(no intercambies cifras). Escribe las cifras en dígitos, nunca en letra. '
        'No inventes cifras, porcentajes, resultados ni rivales. Si mencionas la temporada, '
        'escríbela tal como aparece en HECHOS. Concuerda singular y plural con las cifras.',
        f'3. Menciona a la persona exactamente como {NAME_MARKER}, una vez como mínimo, sin '
        'artículo delante (ni «en» ni «la» en catalán). No añadas contexto que no esté en '
        'HECHOS (familia, emociones concretas, fotos con rivales).',
        '4. No menciones a compañeros ni compares con nadie.',
        '5. Tono positivo, natural, sin exagerar; nunca digas «nuestro equipo».',
        '6. Concordancia de género según "genero" (male, female; mixed o vacío = neutro).',
        f'7. Máximo {payload["max_caracteres"]} caracteres, sin saltos de línea.',
        '8. Devuelve solo JSON con esta forma: {"text": "..."}',
    ])


def _now() -> float:
    return time.time()


def _acquire_lock() -> bool:
    try:
        if cache.add(CACHE_KEY_LOCK, '1', timeout=15):
            return True
        deadline = time.monotonic() + _LOCK_TIMEOUT
        while time.monotonic() < deadline:
            time.sleep(_LOCK_RETRY_DELAY)
            if cache.add(CACHE_KEY_LOCK, '1', timeout=15):
                return True
    except Exception as e:
        logger.warning('Fallo al adquirir el cerrojo de redacción en caché: %s', e)
        return False
    return False


def _release_lock():
    try:
        cache.delete(CACHE_KEY_LOCK)
    except Exception:
        pass


def _throttle():
    """Espacia las llamadas ``LLM_NARRATIVE_MIN_INTERVAL`` s (la capa gratuita de Gemini admite 15/min).

    El límite es compartido entre workers vía caché (Redis en producción).
    0 desactiva la pausa en una cuenta de pago.
    """
    global _last_call
    interval = getattr(settings, 'LLM_NARRATIVE_MIN_INTERVAL', 0)
    if interval <= 0:
        return

    now = _now()
    locked = _acquire_lock()

    if locked:
        try:
            last_call = cache.get(CACHE_KEY_LAST_CALL, 0.0)
            try:
                last_call = float(last_call) if last_call is not None else 0.0
            except (ValueError, TypeError):
                last_call = 0.0

            # Si last_call está en el futuro lejano (> now + 120s) por desajuste de reloj o dato corrupto, resetear.
            if last_call > now + 120.0:
                last_call = 0.0

            target_time = max(now, last_call + interval)
            cache.set(CACHE_KEY_LAST_CALL, target_time, timeout=3600)
            _last_call = target_time
        except Exception as e:
            logger.warning('Error actualizando el throttle compartido en caché: %s', e)
            target_time = max(now, _last_call + interval)
            _last_call = target_time
        finally:
            _release_lock()
    else:
        target_time = max(now, _last_call + interval)
        _last_call = target_time

    wait = target_time - _now()
    if wait > 0:
        time.sleep(wait)


def _post_to_provider(prompt: str) -> str:
    """Única pieza específica del proveedor (Gemini): devuelve el texto crudo del modelo.

    Cambiar de proveedor es reescribir esta función y los valores del ``.env``.
    """
    _throttle()
    url = (
        'https://generativelanguage.googleapis.com/v1beta/models/'
        f'{settings.LLM_NARRATIVE_MODEL}:generateContent'
    )
    headers = {'x-goog-api-key': settings.LLM_NARRATIVE_API_KEY, 'Content-Type': 'application/json'}
    body = {
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {'responseMimeType': 'application/json', 'temperature': 0.7},
    }
    try:
        response = requests.post(url, headers=headers, json=body, timeout=settings.LLM_NARRATIVE_TIMEOUT)
    except requests.exceptions.RequestException as e:
        raise NarrativeTransientError(f'Red o timeout con la API de redacción: {e}')

    if response.status_code in TRANSIENT_HTTP_CODES:
        raise NarrativeTransientError(f'API de redacción HTTP {response.status_code}')
    if response.status_code != 200:
        raise NarrativeError(f'API de redacción HTTP {response.status_code}: {response.text[:300]}')
    try:
        data = response.json()
    except ValueError as e:
        raise NarrativeError(f'La respuesta de la API no es JSON: {e}')
    try:
        return data['candidates'][0]['content']['parts'][0]['text']
    except (KeyError, IndexError, TypeError):
        # 200 sin texto (bloqueo por seguridad, MAX_TOKENS): es el texto lo que no sirve, no la
        # API; descartar evita que la misma fila corte la tanda cada noche.
        raise NarrativeDiscarded(f'Respuesta sin texto utilizable: {str(data)[:200]}')


def _validate(text, payload: dict, max_chars: int) -> str:
    if not isinstance(text, str) or '\n' in text or '\r' in text:
        raise NarrativeDiscarded('Texto no válido o con saltos de línea')
    text = ' '.join(text.split())
    if not text:
        raise NarrativeDiscarded('Texto vacío')
    if NAME_MARKER not in text:
        raise NarrativeDiscarded(f'Falta {NAME_MARKER}')
    if len(text) > max_chars:
        raise NarrativeDiscarded(f'Supera {max_chars} caracteres')
    if re.search(r'[{}]', text.replace(NAME_MARKER, '')):
        raise NarrativeDiscarded('Quedan restos de plantilla')
    # La temporada (2025-26) la menciona el modelo con naturalidad: se quita entera antes de
    # contar cifras, en vez de permitir 2025 y 26 sueltos.
    figures = text.replace(str(payload.get('temporada', '')), '') if payload.get('temporada') else text
    invented = {int(n) for n in re.findall(r'\d+', figures)} - _allowed_numbers(payload)
    if invented:
        raise NarrativeDiscarded(f'Cifras fuera de los hechos: {sorted(invented)}')
    return text


def _allowed_numbers(payload: dict) -> set[int]:
    """Números que el texto puede citar: los de los hechos, salvo temporada y límite.

    Incluye los dígitos de textos como el nombre del equipo («Cadete 2»), que el modelo
    puede repetir tal cual. Techo: no detecta una cifra permutada entre contadores.
    """
    return {
        int(n)
        for key, value in payload.items() if key not in _NON_FIGURE_KEYS
        for n in re.findall(r'\d+', str(value))
    }
