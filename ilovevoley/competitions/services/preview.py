"""Previa de un partido pendiente: historial entre ambos equipos y cómo llegan.

Todo sale de ``Match`` y ``Standing`` ya scrapeados. El número de consultas es
fijo (historial, clasificación y forma de cada equipo), sin N+1.
"""

from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import gettext as _

from ilovevoley.competitions.models import Match, Standing
from ilovevoley.competitions.services.sets import match_set_scores

MAX_HEAD_TO_HEAD = 10
FORM_SIZE = 5


def _finished():
    return Match.objects.filter(
        status='finished', home_score__isnull=False, away_score__isnull=False,
    )


def _won(match, team_id):
    if match.home_team_id == team_id:
        return match.home_score > match.away_score
    return match.away_score > match.home_score


def _form(team_id, before):
    matches = (
        _finished()
        .filter(Q(home_team_id=team_id) | Q(away_team_id=team_id), match_date__lt=before)
        .only('home_team_id', 'away_team_id', 'home_score', 'away_score', 'match_date')
        .order_by('-match_date')[:FORM_SIZE]
    )
    # Del más antiguo al más reciente, como se lee una racha.
    return [_won(m, team_id) for m in reversed(matches)]


def _head_to_head_filter(match):
    """Enfrentamientos entre los dos equipos, también de temporadas anteriores.

    ``Team`` no sirve como identidad entre temporadas: la federación cambia su id
    cada año y el emparejamiento por nombre falla con patrocinadores. Los ids de
    club que trae cada partido de la federación sí son estables, así que se
    cruzan por club dentro de la misma categoría (que ya fija el género). Si un
    club tiene dos equipos en la categoría (Groc/Lila), aparecen ambos; cada
    fila muestra su nombre. Los partidos sin ids de club (RFEVB, amistosos)
    entran por el par de ``Team``.
    """
    home_id, away_id = match.home_team_id, match.away_team_id
    by_team = (
        Q(home_team_id=home_id, away_team_id=away_id)
        | Q(home_team_id=away_id, away_team_id=home_id)
    )
    if match.league_id:
        categories_pks = match.league.categories.values('pk')
        by_team = by_team & (
            Q(league_id=match.league_id)
            | Q(league__categories__in=categories_pks)
            | Q(league__isnull=True)
        )

    local, away = match.federation_club_local_id, match.federation_club_away_id
    # El parser guarda str(None) cuando la federación envía null: no es un club.
    if not (local and away and match.league_id) or {local, away} & {'None', '0'}:
        return by_team
    by_club = (
        Q(federation_club_local_id=local, federation_club_away_id=away)
        | Q(federation_club_local_id=away, federation_club_away_id=local)
    ) & Q(league__categories__in=match.league.categories.values('pk'))
    return by_team | by_club


def build_match_preview(match):
    """Datos de la previa, o ``None`` si no aplica o no hay nada que mostrar."""
    if match.is_finished or not match.home_team_id or not match.away_team_id:
        return None
    home_id, away_id = match.home_team_id, match.away_team_id

    head_to_head = list(
        _finished()
        .filter(_head_to_head_filter(match))
        .exclude(pk=match.pk)
        .select_related('home_team', 'away_team', 'league__season')
        .annotate(
            videos_count=Count('videos', distinct=True),
            images_count=Count('images', distinct=True),
        )
        .distinct()
        .order_by('-match_date')[:MAX_HEAD_TO_HEAD]
    )
    for past in head_to_head:
        past.preview_set_scores = match_set_scores(past)

    positions = {}
    if match.league_id:
        positions = dict(
            Standing.objects.filter(league_id=match.league_id, team_id__in=[home_id, away_id])
            .values_list('team_id', 'position')
        )

    home_form = _form(home_id, match.match_date)
    away_form = _form(away_id, match.match_date)

    if not (head_to_head or positions or home_form or away_form):
        return None
    return {
        'head_to_head': head_to_head,
        'home_position': positions.get(home_id),
        'away_position': positions.get(away_id),
        'home_form': home_form,
        'away_form': away_form,
    }


def preview_card_pills(match):
    """Pastillas de la story previa (#456): hora y posición de ambos en la clasificación.

    La hora 00:00 es la convención de "hora por confirmar" y no se muestra.
    """
    pills = []
    local = timezone.localtime(match.match_date)
    if (local.hour, local.minute) != (0, 0):
        pills.append(local.strftime('%H:%M'))
    if match.league_id:
        positions = dict(
            Standing.objects.filter(
                league_id=match.league_id, team_id__in=[match.home_team_id, match.away_team_id]
            ).values_list('team_id', 'position')
        )
        home, away = positions.get(match.home_team_id), positions.get(match.away_team_id)
        if home is not None and away is not None:
            pills.append(_('%(home)sº vs %(away)sº') % {'home': home, 'away': away})
    return pills
