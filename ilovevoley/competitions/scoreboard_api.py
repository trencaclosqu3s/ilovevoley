"""API del marcador: token, tenant y resolución de partido en un solo camino.

El webhook y los endpoints que vengan después comparten el mismo decorador.
La vista recibe el tenant ya resuelto y no vuelve a mirar el token.
"""

import hmac
import json
import logging
from datetime import timedelta
from functools import wraps
from types import SimpleNamespace

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from ilovevoley.content.models.content import Video
from ilovevoley.videos.scraping.base import validate_volleyball_score

from .models import Match, MatchMark
from .services.notifications import notify_match_result
from .services.preview import build_overlay_preview
from .services.youtube_live import (
    is_live_channel_url,
    is_watch_url,
    resolve_live_watch_url,
)
from .views import _save_stream_url

logger = logging.getLogger(__name__)

# Latido del marcador ~30 s = 3 latidos (D-05); si cambia uno, revisar el otro.
LIVE_STATE_TTL = 90
# Un intento de resolver @canal/live cada ~2 min por partido (D-02).
LIVE_RESOLVE_COOLDOWN = 120
LIVE_MAX_POINTS = 99
LIVE_MAX_SETS = 9
LIVE_MAX_HISTORY = 9
# La previa cambia poco durante el partido (#609): una consulta por emisión basta.
PREVIEW_CACHE_TTL = 300
# Una emisión no pasa de 12 h ni de unos cientos de jugadas marcadas.
MARK_MAX_SECONDS = 12 * 3600
MARK_MAX_PER_MATCH = 500
# El resumen cabe en un partido: 9 sets y unos cientos de puntos, no un volcado libre.
SUMMARY_MAX_BYTES = 48_000
SUMMARY_MAX_TIMELINE = 400


def live_state_key(match_id):
    return f'scoreboard:live:{match_id}'


def live_resolve_cooldown_key(match_id):
    return f'scoreboard:live-resolve:{match_id}'


def _retry_live_resolution(match, tenant):
    """Reintenta ``@canal/live`` durante el directo, como mucho una vez cada 2 min.

    El cooldown se toma antes de resolver: cuenta tanto el fallo como el éxito
    y evita que dos latidos concurrentes resuelvan a la vez. Un fallo aquí no
    puede romper el latido: el estado en vivo ya está guardado.
    """
    try:
        url = (match.stream_url or '').strip()
        if not is_live_channel_url(url):
            return
        if not cache.add(live_resolve_cooldown_key(match.pk), 1, LIVE_RESOLVE_COOLDOWN):
            return
        resolved = resolve_live_watch_url(url)
        if resolved:
            _save_stream_url(match, resolved, tenant)
    except Exception as exc:
        logger.warning(
            "Fallo al reintentar la resolucion del directo del partido %s: %s",
            getattr(match, "pk", None),
            exc.__class__.__name__,
        )


class ScoreboardApiError(Exception):
    """Error de la API con la respuesta JSON ya construida."""

    def __init__(self, payload, status):
        self.response = JsonResponse(payload, status=status)
        self.status = status
        super().__init__(str(payload))


def _parse_json_body(request):
    """Cuerpo JSON objeto. El decorador convierte el error en 400."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        raise ScoreboardApiError({'success': False, 'error': 'invalid json'}, 400)
    if not isinstance(data, dict):
        raise ScoreboardApiError({'success': False, 'error': 'invalid json'}, 400)
    return data


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
    data = _parse_json_body(request)

    raw_url = data.get('url')
    if not isinstance(raw_url, str) or not raw_url.strip():
        return JsonResponse({'success': False, 'error': 'url required'}, status=400)
    stream_url = raw_url.strip()

    match_id = parse_match_id(data)
    match = resolve_match(tenant, match_id)
    resolved = resolve_live_watch_url(stream_url)
    if resolved is not None:
        stream_url = resolved
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


def _rules_payload(league):
    """Reglas de set del formato de la liga, como enteros explícitos para el marcador."""
    match_format = league.match_format if league else 'standard'
    decider_points = 15
    if match_format == 'tournament_3sets':
        sets_to_win = 2
    elif match_format == 'alevin_balear':
        # Se juegan los 3 sets a 25; el tercero no es un decisivo a 15.
        sets_to_win, decider_points = 2, 25
    elif match_format == 'custom':
        sets_to_win = league.custom_sets_to_win or 3
    else:
        sets_to_win = 3
    # La liga no guarda los puntos por set (ej. Balears juega a 15 en primeras fases): siempre 25.
    return {'set_points': 25, 'decider_points': decider_points, 'sets_to_win': sets_to_win}


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
        .select_related('league', 'home_team__club', 'away_team__club')
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
            'rules': _rules_payload(match.league),
            'home_team': _team_payload(request, match.home_team, match.home_team_display),
            'away_team': _team_payload(request, match.away_team, match.away_team_display),
        })
    return JsonResponse({
        'success': True,
        'date': start.date().isoformat(),
        'matches': payload,
    })


def _preview_round(match):
    """Jornada del partido, o None si la liga no usa jornadas.

    ``round_number`` vale 1 por defecto: solo es fiable si algún partido de la
    liga tiene una jornada posterior.
    """
    if not match.league_id:
        return None
    if not Match.objects.filter(league_id=match.league_id, round_number__gt=1).exists():
        return None
    return match.round_number


@scoreboard_api(methods=('GET',))
def api_scoreboard_match_preview(request, tenant):
    """Previa del partido en ventana (o ``?match_id=``): clasificación, forma y H2H."""
    match = resolve_match(tenant, parse_match_id(request.GET))
    if not match.home_team_id or not match.away_team_id:
        raise ScoreboardApiError({'success': False, 'error': 'teams not set'}, 404)

    # Tras resolve_match: el partido ya es del club, la caché no cruza tenants.
    key = f'scoreboard:preview:{match.pk}:{request.get_host()}'
    payload = cache.get(key)
    if payload is None:
        local_date = timezone.localtime(match.match_date)
        payload = {
            'success': True,
            'match': {
                'id': match.pk,
                'match_date': local_date.isoformat(),
                'competition': match.league.display_name if match.league_id else None,
                'round': _preview_round(match),
                'home_team': _team_payload(request, match.home_team, match.home_team_display),
                'away_team': _team_payload(request, match.away_team, match.away_team_display),
            },
            **build_overlay_preview(match),
        }
        cache.set(key, payload, PREVIEW_CACHE_TTL)
    return JsonResponse(payload)


def _is_non_neg_int(value):
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def _parse_result_payload(data):
    """Valida y normaliza (home_score, away_score, set_scores) del marcador (D-05)."""
    home = data.get('home_score')
    away = data.get('away_score')
    if not _is_non_neg_int(home) or not _is_non_neg_int(away):
        raise ScoreboardApiError({'success': False, 'error': 'invalid result'}, 400)

    raw_partials = data.get('set_scores')
    if raw_partials is None or raw_partials == []:
        return home, away, []

    if not isinstance(raw_partials, list) or len(raw_partials) > LIVE_MAX_HISTORY:
        raise ScoreboardApiError({'success': False, 'error': 'invalid result'}, 400)

    partials = []
    home_wins = 0
    away_wins = 0
    for pair in raw_partials:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ScoreboardApiError({'success': False, 'error': 'invalid result'}, 400)
        local_pts, visitor_pts = pair
        if (
            not _is_non_neg_int(local_pts)
            or local_pts > LIVE_MAX_POINTS
            or not _is_non_neg_int(visitor_pts)
            or visitor_pts > LIVE_MAX_POINTS
            or local_pts == visitor_pts
        ):
            raise ScoreboardApiError({'success': False, 'error': 'invalid result'}, 400)
        if local_pts > visitor_pts:
            home_wins += 1
        else:
            away_wins += 1
        partials.append([local_pts, visitor_pts])

    if home_wins > home or away_wins > away:
        raise ScoreboardApiError({'success': False, 'error': 'invalid result'}, 400)

    return home, away, partials


def _parse_summary(raw):
    """Acepta el bloque ``summary`` del marcador o None. Rechaza otra forma."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ScoreboardApiError({'success': False, 'error': 'invalid summary'}, 400)
    sets = raw.get('sets', [])
    if sets is None:
        sets = []
    if not isinstance(sets, list) or len(sets) > LIVE_MAX_HISTORY:
        raise ScoreboardApiError({'success': False, 'error': 'invalid summary'}, 400)
    for item in sets:
        if not isinstance(item, dict):
            raise ScoreboardApiError({'success': False, 'error': 'invalid summary'}, 400)
        timeline = item.get('timeline', [])
        if timeline is None:
            continue
        if not isinstance(timeline, list) or len(timeline) > SUMMARY_MAX_TIMELINE:
            raise ScoreboardApiError({'success': False, 'error': 'invalid summary'}, 400)
        if any(not isinstance(point, dict) for point in timeline):
            raise ScoreboardApiError({'success': False, 'error': 'invalid summary'}, 400)
    try:
        encoded = json.dumps(raw, separators=(',', ':'))
    except (TypeError, ValueError):
        raise ScoreboardApiError({'success': False, 'error': 'invalid summary'}, 400)
    if len(encoded) > SUMMARY_MAX_BYTES:
        raise ScoreboardApiError({'success': False, 'error': 'invalid summary'}, 400)
    return raw


@scoreboard_api()
def api_scoreboard_match_result(request, tenant):
    """Guarda el resultado provisional enviado desde el marcador (#576).

    La federación manda (D-07): si el partido ya tiene ``acta_data``, ``acta_html``
    o ``result_penalized``, responde 409 sin tocar nada. Cuando el scraping
    federativo llega después y difiere del resultado del marcador (D-08 / RES-04),
    ``detect_and_record_match_changes`` registra un ``MatchChangeLog`` con
    ``change_type='score'``, pero los hooks de push solo filtran ``datetime``,
    ``venue`` y ``status``, así que el cambio queda registrado y no se reenvía
    ninguna notificación de corrección.
    """
    data = _parse_json_body(request)

    match_id = parse_match_id(data)
    if match_id is None:
        return JsonResponse({'success': False, 'error': 'match_id required'}, status=400)
    match = resolve_match(tenant, match_id)

    home, away, partials = _parse_result_payload(data)
    league = match.league or SimpleNamespace(match_format='standard')
    if not validate_volleyball_score(home, away, league):
        return JsonResponse({'success': False, 'error': 'invalid score'}, status=400)
    # Un marcador antiguo no manda summary: no se toca el histórico ya guardado.
    # null explícito sí lo borra, para que el marcador pueda retractarlo.
    has_summary = 'summary' in data
    summary = _parse_summary(data.get('summary')) if has_summary else None

    # La comprobación de la federación y el guardado comparten el bloqueo de la
    # fila: si el scraping escribe el acta entre medias, no se pisa.
    with transaction.atomic():
        match = Match.objects.select_for_update().get(pk=match.pk)
        if match.acta_data or match.acta_html or match.result_penalized:
            raise ScoreboardApiError(
                {'success': False, 'error': 'federation result'}, 409
            )
        match.home_score = home
        match.away_score = away
        match.set_scores = partials
        match.status = 'finished'
        update_fields = ['home_score', 'away_score', 'set_scores', 'status']
        if has_summary:
            match.scoreboard_summary = summary
            update_fields.append('scoreboard_summary')
        match.save(update_fields=update_fields)

    notified = False
    try:
        notified = notify_match_result(match, tenant=tenant)
    except Exception:
        logger.exception("Error al notificar el resultado del partido %s", match.pk)

    return JsonResponse({
        'success': True,
        'match_id': match.pk,
        'notified': bool(notified),
    })


@scoreboard_api()
def api_scoreboard_stream_ended(request, tenant):
    """Crea el Video del partido al recibir el aviso de fin del marcador (#577).

    Techo de v1 (D-18): exige ``match_id`` (sin fallback a la ventana, porque
    el partido sale de ``is_live_window`` al pasar a ``finished``). Solo crea
    ``Video`` cuando la URL final es ``watch?v=<id>``; otras URLs responden 200
    con ``created=false`` y ``reason='unsupported url'``.
    """
    data = _parse_json_body(request)

    match_id = parse_match_id(data)
    if match_id is None:
        return JsonResponse({'success': False, 'error': 'match_id required'}, status=400)
    match = resolve_match(tenant, match_id)

    user_id = getattr(settings, 'SCOREBOARD_VIDEO_USER_ID', 0) or 0
    user = get_user_model().objects.filter(pk=user_id).first() if user_id > 0 else None
    if user is None:
        logger.error(
            "SCOREBOARD_VIDEO_USER_ID ausente o sin usuario; no se crea el Video del partido %s",
            match.pk,
        )
        return JsonResponse(
            {'success': False, 'error': 'video user not configured'}, status=503
        )

    url = (match.stream_url or '').strip()
    if not url:
        return JsonResponse({
            'success': True,
            'match_id': match.pk,
            'created': False,
            'reason': 'no stream url',
        })

    if is_live_channel_url(url):
        resolved = resolve_live_watch_url(url)
        if resolved is None:
            return JsonResponse({
                'success': True,
                'match_id': match.pk,
                'created': False,
                'reason': 'unresolved',
            })
        match.stream_url = resolved
        match.save(update_fields=['stream_url'])
        url = resolved
    elif not is_watch_url(url):
        return JsonResponse({
            'success': True,
            'match_id': match.pk,
            'created': False,
            'reason': 'unsupported url',
        })

    base = f'{match.home_team_display} - {match.away_team_display}'
    existing = match.videos.count()
    title = (base if existing == 0 else f'{base} parte {existing + 1}')[:200]
    video, created = Video.objects.get_or_create(match=match, youtube_url=url, defaults={
        'title': title,
        'organization': tenant,
        'created_by': user,
    })

    return JsonResponse({
        'success': True,
        'match_id': match.pk,
        'created': bool(created),
        'video_id': video.pk,
        'stream_url': url,
    })


def _parse_live_state(data):
    """Valida y acota el subconjunto del marcador en vivo (D-06)."""
    home_points = data.get('home_points')
    away_points = data.get('away_points')
    home_sets = data.get('home_sets')
    away_sets = data.get('away_sets')
    if (
        not _is_non_neg_int(home_points)
        or home_points > LIVE_MAX_POINTS
        or not _is_non_neg_int(away_points)
        or away_points > LIVE_MAX_POINTS
        or not _is_non_neg_int(home_sets)
        or home_sets > LIVE_MAX_SETS
        or not _is_non_neg_int(away_sets)
        or away_sets > LIVE_MAX_SETS
    ):
        raise ScoreboardApiError({'success': False, 'error': 'invalid state'}, 400)

    raw_history = data.get('sets_history')
    if not isinstance(raw_history, list) or len(raw_history) > LIVE_MAX_HISTORY:
        raise ScoreboardApiError({'success': False, 'error': 'invalid state'}, 400)

    partials = []
    for pair in raw_history:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ScoreboardApiError({'success': False, 'error': 'invalid state'}, 400)
        local_pts, visitor_pts = pair
        if (
            not _is_non_neg_int(local_pts)
            or local_pts > LIVE_MAX_POINTS
            or not _is_non_neg_int(visitor_pts)
            or visitor_pts > LIVE_MAX_POINTS
            or local_pts == visitor_pts
        ):
            raise ScoreboardApiError({'success': False, 'error': 'invalid state'}, 400)
        partials.append([local_pts, visitor_pts])

    serve = data.get('serve')
    if serve not in (None, 'home', 'away'):
        raise ScoreboardApiError({'success': False, 'error': 'invalid state'}, 400)

    visible = data.get('visible')
    if not isinstance(visible, bool):
        raise ScoreboardApiError({'success': False, 'error': 'invalid state'}, 400)

    return {
        'home_points': home_points,
        'away_points': away_points,
        'home_sets': home_sets,
        'away_sets': away_sets,
        'sets_history': partials,
        'serve': serve,
        'visible': visible,
    }


@scoreboard_api()
def api_scoreboard_live_state(request, tenant):
    """Guarda en caché el estado en vivo del marcador con TTL de 90 s (#578, D-05..D-08)."""
    data = _parse_json_body(request)

    match_id = parse_match_id(data)
    if match_id is None:
        return JsonResponse({'success': False, 'error': 'match_id required'}, status=400)
    match = resolve_match(tenant, match_id)

    if not match.is_live_window:
        raise ScoreboardApiError({'success': False, 'error': 'not live'}, 409)

    subset = _parse_live_state(data)
    cache.set(live_state_key(match.pk), subset, LIVE_STATE_TTL)
    _retry_live_resolution(match, tenant)
    return JsonResponse({'success': True, 'match_id': match.pk})


@scoreboard_api()
def api_scoreboard_match_mark(request, tenant):
    """Guarda una marca de jugada con el segundo de la emisión (#580).

    El segundo lo calcula el marcador desde el inicio real de la emisión. El
    marcador del instante es opcional y usa la forma de ``live-state``.
    """
    data = _parse_json_body(request)
    seconds = data.get('seconds')
    if not _is_non_neg_int(seconds) or seconds > MARK_MAX_SECONDS:
        return JsonResponse({'success': False, 'error': 'invalid seconds'}, status=400)
    state = data.get('state')
    scoreboard = {} if state is None else _parse_live_state(state)

    match = resolve_match(tenant, parse_match_id(data))
    if match.marks.count() >= MARK_MAX_PER_MATCH:
        return JsonResponse({'success': False, 'error': 'too many marks'}, status=409)
    # Mismo (partido, segundo) = reintento del marcador: no duplica.
    mark, created = MatchMark.objects.get_or_create(
        match=match, seconds=seconds, defaults={'scoreboard': scoreboard},
    )
    return JsonResponse({'success': True, 'match_id': match.pk, 'mark_id': mark.pk, 'created': created})


@require_http_methods(['GET'])
def api_live_scoreboard(request, match_id):
    """Lectura pública del marcador en vivo desde la ficha (#578, D-09, D-11, D-14)."""
    match = get_object_or_404(
        Match.objects.only('id', 'status', 'match_date'), pk=match_id
    )
    state = cache.get(live_state_key(match.pk)) if match.is_live_window else None
    if not state or not state.get('visible'):
        response = JsonResponse({'success': True, 'live': False})
    else:
        response = JsonResponse({'success': True, 'live': True, **state})
    response['Cache-Control'] = 'no-store'
    return response
