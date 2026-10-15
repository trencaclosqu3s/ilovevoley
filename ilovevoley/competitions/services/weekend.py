from datetime import datetime, time, timedelta
from typing import Any

from django.core.cache import cache
from django.db.models import Q, QuerySet
from django.utils import timezone

from ilovevoley.competitions.models import Match
from ilovevoley.content.models import Image
from ilovevoley.core.mixins import get_club_team_filter
from ilovevoley.teams.models import Team

UPCOMING_LIMIT = 12
RESULTS_LIMIT = 6
PHOTOS_LIMIT = 6
# Una foto cuenta como «relevante» para activar la entrada solo si es reciente: si no,
# una única foto histórica de un equipo seguido mantendría la pestaña «Este finde» activa
# para siempre.
RELEVANT_PHOTOS_DAYS = 7
# La navegación consulta el resumen en cada render: se cachea por (usuario, club, día)
# unos minutos para no repetir el cálculo en cada página.
ENTRY_CACHE_TTL = 300
_CACHE_MISSING = object()


def _resolve_local_datetime(dt: datetime | None = None) -> datetime:
    """Asegura que la fecha y hora recibida esté en la zona horaria local activa."""
    if dt is None:
        return timezone.localtime()
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return timezone.localtime(dt)


def has_follow_preferences(user, organization) -> bool:
    """Indica si el usuario tiene equipos seguidos o categorías de interés en la organización."""
    if user is None or not getattr(user, 'is_authenticated', True) or organization is None:
        return False

    has_teams = Team.objects.filter(
        followers__user=user,
        followers__organization=organization,
    ).exists()
    if has_teams:
        return True

    return user.preferred_categories_for(organization).exists()


def following_match_filter(user, organization) -> Q:
    """Construye el filtro Q de partidos según las preferencias de seguimiento del usuario.

    Regla de seguimiento (idéntica a UserMatchesFeed):
    - Si el usuario sigue equipos concretos en el club (CategoryPreference.teams no vacío),
      se devuelven los partidos donde juega alguno de esos equipos como local o visitante.
    - Si no sigue equipos pero tiene categorías de interés en el club, se devuelven los partidos
      del club cuya liga esté en esas categorías, más los amistosos del club.
    - Si no hay ni equipos ni categorías, devuelve un Q vacío que no casa nada: Q(pk__in=[]).
    """
    if user is None or not getattr(user, 'is_authenticated', True) or organization is None:
        return Q(pk__in=[])

    followed_teams = Team.objects.filter(
        followers__user=user,
        followers__organization=organization,
    ).distinct()
    if followed_teams.exists():
        return Q(home_team__in=followed_teams) | Q(away_team__in=followed_teams)

    preferred_categories = user.preferred_categories_for(organization)
    if preferred_categories.exists():
        team_filter = get_club_team_filter(organization)
        return (Q(league__categories__in=preferred_categories) | Q(is_friendly=True)) & team_filter

    return Q(pk__in=[])


def weekend_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Calcula los límites temporales del fin de semana (viernes 00:00:00 a domingo 23:59:59.999999).

    Zona horaria local de Django (Europe/Madrid).
    - Lunes a jueves: el viernes siguiente.
    - Viernes, sábado y domingo: el fin de semana en curso.
    """
    local_now = _resolve_local_datetime(now)
    weekday = local_now.weekday()  # 0=lunes, ..., 6=domingo

    if weekday in (4, 5, 6):
        friday_date = local_now.date() - timedelta(days=(weekday - 4))
    else:
        friday_date = local_now.date() + timedelta(days=(4 - weekday))

    sunday_date = friday_date + timedelta(days=2)

    tz = timezone.get_current_timezone()
    window_start = timezone.make_aware(datetime.combine(friday_date, time.min), tz)
    window_end = timezone.make_aware(datetime.combine(sunday_date, time.max), tz)

    return window_start, window_end


def weekend_variant(now: datetime | None = None) -> str:
    """Variante temporal de la vista según el día de la semana.

    - 'summary': lunes (resumen del fin de semana cerrado).
    - 'live': viernes, sábado y domingo (fin de semana en juego).
    - 'upcoming': martes, miércoles y jueves (previa del próximo fin de semana).
    """
    local_now = _resolve_local_datetime(now)
    weekday = local_now.weekday()

    if weekday == 0:
        return 'summary'
    if weekday in (4, 5, 6):
        return 'live'
    return 'upcoming'


def _upcoming_matches_queryset(user, organization, now: datetime | None = None) -> QuerySet[Match]:
    """QuerySet base no acotado para próximos partidos programados o en progreso.

    Sin preferencias de seguimiento ``following_match_filter`` no casa nada, así que
    no hace falta un guardia previo con su propia consulta.
    """
    current_now = _resolve_local_datetime(now)
    start_dt, end_dt = weekend_bounds(current_now)

    base_qs = Match.objects.filter(
        following_match_filter(user, organization),
        status__in=['scheduled', 'in_progress'],
    )

    weekend_qs = base_qs.filter(match_date__gte=start_dt, match_date__lte=end_dt)
    if weekend_qs.exists():
        return weekend_qs

    # Si la ventana del fin de semana no tiene partidos, se amplía a los próximos 7 días
    return base_qs.filter(
        match_date__gte=current_now,
        match_date__lte=current_now + timedelta(days=7),
    )


def upcoming_matches(user, organization, now: datetime | None = None) -> QuerySet[Match]:
    """Próximos partidos relevantes programados o en juego para el usuario y organización.

    Filtra por partidos en la ventana de fin de semana actual o próximo. Si esa ventana
    queda vacía, amplía a los próximos 7 días desde now. Orden ascendente por match_date
    y limitado a 12 partidos.
    """
    qs = _upcoming_matches_queryset(user, organization, now=now)
    return qs.select_related(
        'home_team', 'away_team', 'league'
    ).prefetch_related(
        'league__categories'
    ).distinct().order_by('match_date')[:UPCOMING_LIMIT]


def _recent_results_queryset(user, organization, now: datetime | None = None) -> QuerySet[Match]:
    """QuerySet base no acotado para partidos finalizados en los últimos 7 días."""
    current_now = _resolve_local_datetime(now)
    start_date = current_now - timedelta(days=7)

    return Match.objects.filter(
        following_match_filter(user, organization),
        status='finished',
        match_date__gte=start_date,
        match_date__lte=current_now,
    )


def recent_results(user, organization, now: datetime | None = None) -> QuerySet[Match]:
    """Partidos finalizados de interés del usuario en los últimos 7 días.

    Orden descendente por match_date y limitado a 6 partidos.
    """
    qs = _recent_results_queryset(user, organization, now=now)
    return qs.select_related(
        'home_team', 'away_team', 'league'
    ).prefetch_related(
        'league__categories'
    ).distinct().order_by('-match_date')[:RESULTS_LIMIT]


def _relevant_photos_q(user, organization) -> Q | None:
    """Construye la condición Q para identificar fotos relevantes al seguimiento del usuario.

    Devuelve None si el usuario no tiene preferencias en la organización (evita que un Q vacío
    case con todas las imágenes del club).
    """
    if user is None or not getattr(user, 'is_authenticated', True) or organization is None:
        return None

    followed_teams = Team.objects.filter(
        followers__user=user,
        followers__organization=organization,
    ).distinct()
    has_teams = followed_teams.exists()

    preferred_categories = user.preferred_categories_for(organization)
    has_categories = preferred_categories.exists()

    if not has_teams and not has_categories:
        return None

    rel_q = Q()
    if has_teams:
        rel_q |= Q(match__home_team__in=followed_teams) | Q(match__away_team__in=followed_teams)
    if has_categories:
        rel_q |= Q(categories__in=preferred_categories)

    return rel_q


def recent_photos(user, organization, limit: int = PHOTOS_LIMIT) -> list[Image] | QuerySet[Image]:
    """Fotos recientes aprobadas del club, priorizando las relevantes según seguimiento.

    Primero fotos con partidos de los equipos seguidos o de categorías preferidas,
    y completa con las últimas del club hasta alcanzar el límite.
    """
    base_images = Image.objects.filter(
        organization=organization,
        status='approved',
    )

    rel_q = _relevant_photos_q(user, organization)
    if rel_q is not None:
        relevant_qs = base_images.filter(rel_q).select_related(
            'match', 'uploaded_by'
        ).distinct().order_by('-upload_date')[:limit]
        photos = list(relevant_qs)

        if len(photos) < limit:
            needed = limit - len(photos)
            already_ids = [p.id for p in photos]
            fill_qs = base_images.exclude(id__in=already_ids).select_related(
                'match', 'uploaded_by'
            ).distinct().order_by('-upload_date')[:needed]
            photos.extend(list(fill_qs))
        return photos

    return list(
        base_images.select_related('match', 'uploaded_by').distinct().order_by('-upload_date')[:limit]
    )


def _has_relevant_photos(user, organization, now: datetime) -> bool:
    """¿Hay fotos aprobadas **recientes** que casen con el seguimiento del usuario?

    Acotar por fecha evita que una única foto histórica mantenga activa la entrada
    «Este finde» de forma permanente. No cuenta el relleno (fotos del club sin
    relación con el seguimiento).
    """
    rel_q = _relevant_photos_q(user, organization)
    if rel_q is None:
        return False
    return Image.objects.filter(
        organization=organization,
        status='approved',
        upload_date__gte=now - timedelta(days=RELEVANT_PHOTOS_DAYS),
    ).filter(rel_q).exists()


def _entry_cache_key(user, organization, now: datetime) -> str:
    return f'weekend_entry:{organization.pk}:{user.pk}:{now.date().isoformat()}'


def _entry_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        'has_content': payload['has_content'],
        'variant': payload['variant'],
        'upcoming_count': payload['upcoming_count'],
    }


def _prime_entry_cache(user, organization, payload: dict[str, Any], now: datetime) -> None:
    """Deja cacheado el resumen ligero para que la navegación no lo recalcule.

    La vista de /finde/ ya calcula el overview, así que sembrar aquí la caché evita
    pagar dos veces el mismo trabajo en esa página.
    """
    if organization is None or user is None or not getattr(user, 'is_authenticated', False):
        return
    cache.set(_entry_cache_key(user, organization, now), _entry_payload(payload), ENTRY_CACHE_TTL)


def weekend_overview(user, organization, now: datetime | None = None) -> dict[str, Any]:
    """Vista agregada completa de la pantalla «Este finde».

    Devuelve un diccionario con exactamente las claves:
    variant, has_content, upcoming_count, upcoming, results, photos, window_start, window_end.
    """
    current_now = _resolve_local_datetime(now)
    window_start, window_end = weekend_bounds(current_now)

    upcoming = list(upcoming_matches(user, organization, now=current_now))
    results = list(recent_results(user, organization, now=current_now))
    photos = recent_photos(user, organization, limit=PHOTOS_LIMIT)

    # El relleno de fotos no cuenta para has_content; solo las relevantes y recientes.
    has_content = bool(
        upcoming or results or _has_relevant_photos(user, organization, current_now)
    )
    upcoming_count = len(upcoming)

    variant = weekend_variant(current_now)
    if variant == 'summary' and not results:
        # Si es lunes pero no hay resultados del finde que resumir, degradamos a 'upcoming'
        # para mostrar la previa del fin de semana entrante (o su estado vacío).
        variant = 'upcoming'

    payload = {
        'variant': variant,
        'has_content': has_content,
        'upcoming_count': upcoming_count,
        'upcoming': upcoming,
        'results': results,
        'photos': photos,
        'window_start': window_start,
        'window_end': window_end,
    }
    _prime_entry_cache(user, organization, payload, current_now)
    return payload


def weekend_entry(user, organization, now: datetime | None = None) -> dict[str, Any] | None:
    """Versión ligera para la barra de navegación y el card del sidebar.

    - None si el usuario no tiene preferencias de seguimiento en el club.
    - Dict {'has_content': bool, 'variant': str, 'upcoming_count': int}, cacheado
      por (usuario, club, día) para no repetir consultas en cada render.
    """
    if user is None or not getattr(user, 'is_authenticated', False) or organization is None:
        return None

    current_now = _resolve_local_datetime(now)
    cache_key = _entry_cache_key(user, organization, current_now)
    cached = cache.get(cache_key, _CACHE_MISSING)
    if cached is not _CACHE_MISSING:
        return cached

    if not has_follow_preferences(user, organization):
        cache.set(cache_key, None, ENTRY_CACHE_TTL)
        return None

    upcoming_count = min(
        _upcoming_matches_queryset(user, organization, now=current_now).distinct().count(),
        UPCOMING_LIMIT,
    )
    has_results = _recent_results_queryset(user, organization, now=current_now).exists()

    variant = weekend_variant(current_now)
    if variant == 'summary' and not has_results:
        # En lunes sin resultados, degradamos a previa
        variant = 'upcoming'

    payload = {
        'has_content': bool(
            upcoming_count or has_results or _has_relevant_photos(user, organization, current_now)
        ),
        'variant': variant,
        'upcoming_count': upcoming_count,
    }
    cache.set(cache_key, payload, ENTRY_CACHE_TTL)
    return payload
