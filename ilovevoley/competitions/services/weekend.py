from datetime import datetime, time, timedelta
from typing import Any

from django.db.models import Q, QuerySet
from django.utils import timezone

from ilovevoley.competitions.models import Match
from ilovevoley.content.models import Image
from ilovevoley.core.mixins import get_club_team_filter
from ilovevoley.teams.models import Team


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
    """QuerySet base no acotado para próximos partidos programados o en progreso."""
    if not has_follow_preferences(user, organization):
        return Match.objects.none()

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
    if not qs.exists():
        return Match.objects.none()

    return qs.select_related(
        'home_team', 'away_team', 'league'
    ).prefetch_related(
        'league__categories'
    ).distinct().order_by('match_date')[:12]


def _recent_results_queryset(user, organization, now: datetime | None = None) -> QuerySet[Match]:
    """QuerySet base no acotado para partidos finalizados en los últimos 7 días."""
    if not has_follow_preferences(user, organization):
        return Match.objects.none()

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
    if not qs.exists():
        return Match.objects.none()

    return qs.select_related(
        'home_team', 'away_team', 'league'
    ).prefetch_related(
        'league__categories'
    ).distinct().order_by('-match_date')[:6]


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


def recent_photos(user, organization, limit: int = 6) -> list[Image] | QuerySet[Image]:
    """Fotos recientes aprobadas del club, priorizando las relevantes según seguimiento.

    Primero fotos con partidos de los equipos seguidos o de categorías preferidas,
    y completa con las últimas del club hasta alcanzar el límite.
    """
    if organization is None or limit <= 0:
        return []

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


def weekend_overview(user, organization, now: datetime | None = None) -> dict[str, Any]:
    """Vista agregada completa de la pantalla «Este finde».

    Devuelve un diccionario con exactamente las claves:
    variant, has_content, upcoming_count, upcoming, results, photos, window_start, window_end.
    """
    current_now = _resolve_local_datetime(now)
    window_start, window_end = weekend_bounds(current_now)

    upcoming = list(upcoming_matches(user, organization, now=current_now))
    results = list(recent_results(user, organization, now=current_now))
    photos = recent_photos(user, organization, limit=6)

    # Las fotos de relleno no cuentan para has_content: solo si hay fotos que casen
    # explícitamente con las preferencias de seguimiento del usuario.
    rel_q = _relevant_photos_q(user, organization)
    has_relevant_photos = (
        Image.objects.filter(organization=organization, status='approved').filter(rel_q).exists()
        if rel_q is not None
        else False
    )

    has_content = bool(upcoming or results or has_relevant_photos)
    upcoming_count = len(upcoming)

    variant = weekend_variant(current_now)
    if variant == 'summary' and not results:
        # Si es lunes pero no hay resultados del finde que resumir, degradamos a 'upcoming'
        # para mostrar la previa del fin de semana entrante (o su estado vacío).
        variant = 'upcoming'

    return {
        'variant': variant,
        'has_content': has_content,
        'upcoming_count': upcoming_count,
        'upcoming': upcoming,
        'results': results,
        'photos': photos,
        'window_start': window_start,
        'window_end': window_end,
    }


def weekend_entry(user, organization, now: datetime | None = None) -> dict[str, Any] | None:
    """Versión optimizada y ligera para la barra de navegación y el card del sidebar.

    - None si el usuario no tiene preferencias de seguimiento en el club.
    - Dict {'has_content': bool, 'variant': str, 'upcoming_count': int} calculado con .exists() y .count().
    """
    if not has_follow_preferences(user, organization):
        return None

    current_now = _resolve_local_datetime(now)
    upcoming_qs = _upcoming_matches_queryset(user, organization, now=current_now)
    has_upcoming = upcoming_qs.exists()
    upcoming_count = upcoming_qs.distinct().count()

    results_qs = _recent_results_queryset(user, organization, now=current_now)
    has_results = results_qs.exists()

    rel_q = _relevant_photos_q(user, organization)
    has_relevant_photos = (
        Image.objects.filter(organization=organization, status='approved').filter(rel_q).exists()
        if rel_q is not None
        else False
    )

    has_content = bool(has_upcoming or has_results or has_relevant_photos)

    variant = weekend_variant(current_now)
    if variant == 'summary' and not has_results:
        # En lunes sin resultados, degradamos a previa
        variant = 'upcoming'

    return {
        'has_content': has_content,
        'variant': variant,
        'upcoming_count': upcoming_count,
    }
