"""API del marcador: token, tenant y resolución de partido en un solo camino.

El webhook y los endpoints que vengan después comparten el mismo decorador.
La vista recibe el tenant ya resuelto y no vuelve a mirar el token.
"""

import hmac
import json
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import Match
from .views import _save_stream_url


class ScoreboardApiError(Exception):
    """Error de la API con la respuesta JSON ya construida."""

    def __init__(self, payload, status):
        self.response = JsonResponse(payload, status=status)
        self.status = status
        super().__init__(str(payload))


def scoreboard_api(methods=('POST',)):
    """Exige método, Bearer token y tenant antes de llamar a la vista.

    Orden: csrf_exempt, require_http_methods (405), token, tenant.
    Un token vacío en settings rechaza siempre: ``Bearer `` no es válido.
    La vista se invoca como ``view(request, tenant)``.
    """

    def decorator(view):
        @csrf_exempt
        @require_http_methods(methods)
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            token = settings.SCOREBOARD_STREAM_TOKEN
            auth = request.headers.get('Authorization', '')
            if not token or not hmac.compare_digest(
                auth.encode(), f'Bearer {token}'.encode()
            ):
                return JsonResponse({'success': False, 'error': 'forbidden'}, status=403)

            tenant = getattr(request, 'tenant', None)
            if tenant is None:
                return JsonResponse({'success': False, 'error': 'tenant required'}, status=400)

            try:
                return view(request, tenant, *args, **kwargs)
            except ScoreboardApiError as exc:
                return exc.response

        return wrapper

    return decorator


def parse_match_id(data):
    """Devuelve None si falta o es null; solo admite enteros (no bool) o dígitos."""
    if 'match_id' not in data or data['match_id'] is None:
        return None
    value = data['match_id']
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ScoreboardApiError({'success': False, 'error': 'invalid match_id'}, 400)
    if isinstance(value, str):
        if not value.isdigit():
            raise ScoreboardApiError({'success': False, 'error': 'invalid match_id'}, 400)
        return int(value)
    return value


def resolve_match(tenant, match_id=None):
    """Localiza el partido del club. Con id no hay fallback a la ventana.

    Sin id se mantiene la regla de #575: exactamente un partido en ventana.
    Con id se devuelve el partido del club aunque esté finalizado o fuera
    de ventana; otro club o un id inexistente es 404.
    """
    if match_id is not None:
        match = Match.objects.for_tenant(tenant).filter(pk=match_id).first()
        if match is None:
            raise ScoreboardApiError({'success': False, 'error': 'match not found'}, 404)
        return match

    now = timezone.now()
    candidates = Match.objects.for_tenant(tenant).filter(
        match_date__range=(now - timedelta(hours=3), now + timedelta(minutes=30)),
    )
    live = [match for match in candidates if match.is_live_window]
    if len(live) != 1:
        raise ScoreboardApiError(
            {'success': False, 'matches_in_window': len(live)}, 409
        )
    return live[0]


@scoreboard_api()
def api_scoreboard_stream_live(request, tenant):
    """Guarda el directo del partido indicado, o del único en ventana si no hay id."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'invalid json'}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({'success': False, 'error': 'invalid json'}, status=400)

    stream_url = (data.get('url') or '').strip()
    if not stream_url:
        return JsonResponse({'success': False, 'error': 'url required'}, status=400)

    match_id = parse_match_id(data)
    match = resolve_match(tenant, match_id)
    return _save_stream_url(match, stream_url, tenant)
