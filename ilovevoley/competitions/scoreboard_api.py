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

    raw_url = data.get('url')
    if not isinstance(raw_url, str) or not raw_url.strip():
        return JsonResponse({'success': False, 'error': 'url required'}, status=400)
    stream_url = raw_url.strip()

    match_id = parse_match_id(data)
    match = resolve_match(tenant, match_id)
    return _save_stream_url(match, stream_url, tenant)


def _active_organization(team):
    """Primera organización activa del club, ya precargada. Sin club, None."""
    club = team.club
    if club is None:
        return None
    for organization in club.organizations.all():
        if organization.is_active:
            return organization
    return None


def _absolute_logo(request, team):
    """URL absoluta del escudo: el del equipo, si no el del club, si no None."""
    image = team.logo
    if not image and team.club_id and team.club.logo:
        image = team.club.logo
    if not image:
        return None
    return request.build_absolute_uri(image.url)


def _team_payload(request, team, fallback_name):
    """Nombre, escudo y colores del equipo. Sin ficha, solo el nombre de texto."""
    if team is None:
        return {
            'name': fallback_name,
            'logo': None,
            'primary_color': None,
            'secondary_color': None,
        }
    organization = _active_organization(team)
    primary = organization.primary_color if organization else None
    secondary = organization.secondary_color if organization else None
    return {
        'name': team.name,
        'logo': _absolute_logo(request, team),
        'primary_color': primary or None,
        'secondary_color': secondary or None,
    }


@scoreboard_api(methods=('GET',))
def api_scoreboard_matches_today(request, tenant):
    """Partidos de hoy del club, en el día natural de Europe/Madrid."""
    start = timezone.localtime(timezone.now()).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end = start + timedelta(days=1)
    matches = (
        Match.objects.for_tenant(tenant)
        .exclude(status__in=['finished', 'cancelled', 'postponed'])
        .filter(match_date__gte=start, match_date__lt=end)
        .select_related('home_team__club', 'away_team__club')
        .prefetch_related(
            'home_team__club__organizations',
            'away_team__club__organizations',
        )
        .order_by('match_date')
    )
    payload = []
    for match in matches:
        local_date = timezone.localtime(match.match_date)
        payload.append({
            'id': match.pk,
            'match_date': local_date.isoformat(),
            'time': local_date.strftime('%H:%M'),
            'status': match.status,
            'home_team': _team_payload(request, match.home_team, match.home_team_display),
            'away_team': _team_payload(request, match.away_team, match.away_team_display),
        })
    return JsonResponse({
        'success': True,
        'date': start.date().isoformat(),
        'matches': payload,
    })
