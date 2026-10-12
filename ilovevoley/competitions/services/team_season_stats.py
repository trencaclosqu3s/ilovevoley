from __future__ import annotations

from typing import Any

from django.utils import timezone

from ilovevoley.competitions.models import Standing
from ilovevoley.core.models import Season
from ilovevoley.teams.models import Team


def _standing_sort_key(standing: Standing) -> tuple[int, Any, int]:
    dt = standing.updated_at
    if dt is not None and timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return (
        standing.played if standing.played is not None else 0,
        dt if dt is not None else timezone.datetime.min.replace(tzinfo=timezone.utc),
        standing.pk or 0,
    )


def get_team_season_summary(identity: Any, season: Any, tenant: Any) -> dict[str, int] | None:
    """Return aggregated season summary for a team identity scoped to a tenant.

    Queries Standing for Team rows with that identity in leagues of the given season,
    scoped with Standing.objects.for_tenant(tenant).
    Aggregates won, lost, sets_for, sets_against, points_for, points_against, total_points.
    Derives set_difference and point_difference.
    Takes position from the Standing with highest played, breaking ties with newest updated_at.

    Returns None if no standings are found.
    Exposes ONLY keys: position, won, lost, sets_for, sets_against, set_difference,
    points_for, points_against, point_difference, total_points. Never exposes played.
    """
    if not identity or not season or not tenant:
        return None

    if isinstance(identity, Team):
        identity = identity.identity
        if not identity:
            return None

    if isinstance(season, str):
        season = Season.objects.resolve(season)
        if not season:
            return None

    raw_standings = list(
        Standing.objects.for_tenant(tenant)
        .filter(team__identity=identity, league__season=season)
        .order_by("-played", "-updated_at", "-id")
    )
    if not raw_standings:
        return None

    seen_ids = set()
    standings: list[Standing] = []
    for s in raw_standings:
        if s.pk not in seen_ids:
            seen_ids.add(s.pk)
            standings.append(s)

    if not standings:
        return None

    best_standing = max(standings, key=_standing_sort_key)

    won = sum(s.won or 0 for s in standings)
    lost = sum(s.lost or 0 for s in standings)
    sets_for = sum(s.sets_for or 0 for s in standings)
    sets_against = sum(s.sets_against or 0 for s in standings)
    points_for = sum(s.points_for or 0 for s in standings)
    points_against = sum(s.points_against or 0 for s in standings)
    total_points = sum(s.total_points or 0 for s in standings)

    return {
        "position": best_standing.position,
        "won": won,
        "lost": lost,
        "sets_for": sets_for,
        "sets_against": sets_against,
        "set_difference": sets_for - sets_against,
        "points_for": points_for,
        "points_against": points_against,
        "point_difference": points_for - points_against,
        "total_points": total_points,
    }
