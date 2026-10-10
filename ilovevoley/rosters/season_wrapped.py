"""Wrapped de temporada (#458): cifras congeladas al cierre y pantallas que las muestran."""
from dataclasses import dataclass

from django.db.models import Q
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from ilovevoley.competitions.models import League
from ilovevoley.competitions.services.lineups import _played_official_lineups
from ilovevoley.content.favorites import annotate_favorites
from ilovevoley.content.models import Image
from ilovevoley.rosters.player_card import card_photo_allowed

TOP_PHOTOS = 5


def OFFICIAL_CAPTION():  # noqa: N802 — se evalúa en cada idioma activo
    return _('Partidos oficiales · según actas')


@dataclass
class Screen:
    kind: str
    title: str
    value: str = ''
    subtitle: str = ''
    caption: str = ''
    photo_id: int | None = None
    crest_team_id: int | None = None


def _visible_top_photo_id(wrapped, user, tenant):
    """Primera foto candidata que sigue aprobada, etiquetada y permitida por el consentimiento."""
    person = wrapped.person
    ids = wrapped.stats.get('top_photo_ids') or []
    if not ids or not card_photo_allowed(user, person):
        return None
    alive = set(
        Image.objects.for_tenant(tenant).filter(persons=person, status='approved', id__in=ids)
        .values_list('id', flat=True)
    )
    return next((i for i in ids if i in alive), None)


def build_screens(wrapped, user, tenant):
    """Pantallas del Wrapped: alimentan el visor y los PNG, así que ambos coinciden."""
    stats = wrapped.stats
    caption = OFFICIAL_CAPTION()
    screens = [Screen('cover', wrapped.person.full_name, wrapped.season.name, _('Tu temporada'))]
    if stats['matches']:
        screens.append(Screen('matches', _('Has jugado'), str(stats['matches']),
                              ngettext('partido oficial', 'partidos oficiales', stats['matches']), caption))
        if stats['sets']:
            screens.append(Screen('sets', _('Has disputado'), str(stats['sets']),
                                  ngettext('set', 'sets', stats['sets']), caption))
        if stats['wins']:
            screens.append(Screen('wins', _('Estuviste en'), str(stats['wins']),
                                  ngettext('victoria', 'victorias', stats['wins']), caption))
        if stats['rival']:
            screens.append(Screen('rival', _('Tu rival más repetido'), stats['rival']['name'],
                                  ngettext('%(n)s partido', '%(n)s partidos', stats['rival']['matches'])
                                  % {'n': stats['rival']['matches']}, caption,
                                  crest_team_id=stats['rival'].get('team_id')))
    if stats['photos_count']:
        screens.append(Screen('photos', _('Has salido en'), str(stats['photos_count']),
                              ngettext('foto', 'fotos', stats['photos_count'])))
        photo_id = _visible_top_photo_id(wrapped, user, tenant)
        if photo_id:
            screens.append(Screen('top_photo', _('Tu foto más votada'), photo_id=photo_id))
    screens.append(Screen('closing', _('¡Gracias por la temporada!'), '', _('Nos vemos en la próxima')))
    return screens


def _season_images(person, season, modality):
    images = Image.objects.filter(persons=person, status='approved', season=season)
    if modality == League.MODALITY_BEACH:
        return images.filter(match__league__modality=League.MODALITY_BEACH)
    return images.filter(Q(match__isnull=True) | Q(match__league__modality=League.MODALITY_INDOOR))


def build_wrapped_stats(person, season, modality=League.MODALITY_INDOOR):
    """Cifras del jugador en la temporada y modalidad, o ``None`` si no hay nada que contar.

    El rival es el **equipo** (nunca un jugador): el Wrapped se comparte en redes y el
    acta trae nombre y dorsal de menores de otros clubes.
    """
    lineups = list(
        _played_official_lineups(person, modality)
        .filter(match__league__season=season)
        .select_related('match__home_team__identity', 'match__away_team__identity')
    )
    images = _season_images(person, season, modality)
    photos_count = images.count()
    if not lineups and not photos_count:
        return None

    wins = 0
    rival_matches = {}
    rival_names = {}
    rival_team_ids = {}
    for row in lineups:
        match = row.match
        own_home = match.home_team_id == row.team_id
        rival = match.away_team if own_home else match.home_team
        key = rival.identity_id or f'team-{rival.id}'
        rival_names[key] = rival.identity.core_name if rival.identity else rival.name
        rival_team_ids[key] = rival.id
        rival_matches[key] = rival_matches.get(key, 0) + 1
        if match.status == 'finished' and match.home_score is not None and match.away_score is not None:
            wins += (match.home_score > match.away_score) == own_home

    rival = None
    if rival_matches:
        key = min(rival_matches, key=lambda k: (-rival_matches[k], rival_names[k]))
        rival = {'name': rival_names[key], 'matches': rival_matches[key], 'team_id': rival_team_ids[key]}

    top_photo_ids = list(
        annotate_favorites(images, None)
        .filter(favorite_count__gt=0)
        .order_by('-favorite_count', '-upload_date')
        .values_list('id', flat=True)[:TOP_PHOTOS]
    )
    return {
        'matches': len(lineups),
        'sets': sum(row.sets_played or 0 for row in lineups),
        'wins': wins,
        'rival': rival,
        'photos_count': photos_count,
        'top_photo_ids': top_photo_ids,
    }
