"""Fichas provisionales a partir de los dorsales leídos en las actas (#569).

El acta federativa trae dorsal y apellido, casi nunca nombre ni año. Cuando el
club aún no tiene cargada la plantilla, esos dorsales no resuelven a ninguna
ficha y la familia no puede vincularse: ``PersonLinkRequest`` identifica la
ficha por nombre, apellidos y año exactos.

Este módulo propone esos huecos (dorsales con acta y sin rol) y los convierte en
fichas provisionales con su ``PlayerRole``, para que el vínculo self-service sea
posible después. La creación la confirma siempre una persona: el apellido del
acta no basta para dar por buena una identidad.
"""

from django.db import IntegrityError, transaction
from django.utils.translation import gettext as _

from ilovevoley.core.tenant_utils import person_belongs_to_tenant
from ilovevoley.rosters.models import Person, PlayerRole
from ilovevoley.teams.models import Team

from ..models import MatchLineup
from .lineups import _names_match, relink_orphan_lineups


def is_club_team(team):
    """¿El equipo pertenece a algún club activo de la plataforma?

    Los equipos rivales no entran: sus fichas son menores de otros clubes y este
    flujo solo debe crear plantilla propia.
    """
    from ilovevoley.core.models import Organization

    if team is None or not team.identity_id:
        return False
    return any(
        Team.objects.for_tenant(org).filter(pk=team.pk).exists()
        for org in Organization.objects.filter(is_active=True)
    )


def _acta_name(identity, season, jersey):
    """Apellido leído en el acta para un dorsal, o ``''`` si no hay ninguno.

    Es la fuente de verdad para autorizar la reutilización de una ficha: el
    apellido que llega del formulario es editable y no sirve como permiso.
    """
    names = (
        MatchLineup.objects
        .filter(team__identity=identity, jersey_number=jersey)
        .exclude(match__status='withdrawn')
        .filter(match__league__season=season)
        .exclude(name_acta='')
        .order_by('match__match_date', 'match__id')
        .values_list('name_acta', flat=True)
    )
    return (names.last() or '').strip()


def acta_roster_gaps(identity, season):
    """Dorsales con acta y sin rol en la plantilla de (identidad, temporada).

    Solo cuenta filas sin persona resuelta: un enlace manual ya dice a quién
    corresponde el dorsal aunque no haya rol con ese número (#570). Los dorsales
    con rol tampoco son hueco, aunque sus actas se guardaran antes del alta.
    """
    if identity is None or season is None:
        return []

    lines = (
        MatchLineup.objects
        .filter(
            team__identity=identity,
            jersey_number__isnull=False,
            person__isnull=True,
        )
        .exclude(match__status='withdrawn')
        .filter(match__league__season=season)
        .select_related('match')
        .order_by('match__match_date', 'match__id')
    )
    taken = set(
        PlayerRole.objects
        .filter(identity=identity, season=season)
        .exclude(jersey_number__isnull=True)
        .values_list('jersey_number', flat=True)
    )

    gaps = {}
    for line in lines:
        if line.jersey_number in taken:
            continue
        gap = gaps.setdefault(line.jersey_number, {
            'jersey_number': line.jersey_number,
            'name_acta': '',
            'appearances': 0,
        })
        gap['appearances'] += 1
        if (line.name_acta or '').strip():
            # El acta más reciente manda: corrige erratas de las anteriores.
            gap['name_acta'] = line.name_acta.strip()
    return sorted(gaps.values(), key=lambda gap: gap['jersey_number'])


def person_candidates(name_acta, tenant, in_club=None, limit=8):
    """Fichas **del club** que podrían ser el jugador del acta, para no duplicarlo.

    Solo mira fichas que ya ve el club: las de otro club no se enseñan ni se
    adoptan por aquí. Ese caso tiene su propio flujo, ``person_adopt``, que exige
    nombre y año exactos justamente para no convertir esto en un buscador de
    menores de otros clubes.

    ``in_club`` reutiliza la lista del club ya cargada: sin él se relee en cada
    llamada, y la plantilla pide candidatos por cada dorsal del acta.
    """
    if not (name_acta or '').strip():
        return []

    if in_club is None:
        in_club = list(Person.objects.for_tenant(tenant))
    found = {}
    for person in in_club:
        if _names_match(name_acta, person.last_name, person.first_name):
            found[person.pk] = {'person': person}
        if len(found) >= limit:
            break
    return list(found.values())


def create_roster_players(identity, season, tenant, selections):
    """Da de alta los dorsales elegidos y devuelve un resumen del resultado.

    Cada selección es ``{'jersey': int, 'last_name': str, 'person_id': int|None}``.
    Se procesa fila a fila en su propia transacción: un dorsal que acaba de
    ocupar otro usuario no debe tirar el resto del alta. Sin ``person_id`` se
    crea una ficha provisional nueva; no se reutiliza por apellido, porque dos
    jugadores del mismo equipo pueden compartir apellido. Con ``person_id`` la
    ficha elegida tiene que estar activa y casar con el apellido del acta.
    """
    created = 0
    reused = 0
    errors = []

    for selection in selections:
        jersey = selection.get('jersey')
        if not isinstance(jersey, int) or not 0 <= jersey <= 99:
            errors.append(_('Dorsal no válido: %(jersey)s.') % {'jersey': jersey})
            continue

        action = None
        try:
            with transaction.atomic():
                person = None
                person_id = selection.get('person_id')
                if person_id:
                    # El pk llega del formulario: solo vale si la ficha es del
                    # club, sigue activa y su apellido es el que dice el acta.
                    # Sin esto se podría adoptar por pk cualquier ficha ajena,
                    # que es lo que evita ``person_adopt``.
                    person = Person._base_manager.filter(pk=person_id, is_active=True).first()
                    acta_name = _acta_name(identity, season, jersey)
                    if (
                        person is None
                        or not acta_name
                        or not person_belongs_to_tenant(person, tenant)
                        or not _names_match(acta_name, person.last_name, person.first_name)
                    ):
                        errors.append(
                            _('La ficha elegida para el dorsal %(jersey)s no coincide con el acta.')
                            % {'jersey': jersey}
                        )
                        continue
                    action = 'reused'
                else:
                    last_name = (selection.get('last_name') or '').strip()
                    max_length = Person._meta.get_field('last_name').max_length
                    if not last_name:
                        errors.append(
                            _('El dorsal %(jersey)s no tiene apellido con el que crear la ficha.') % {'jersey': jersey}
                        )
                        continue
                    if len(last_name) > max_length:
                        errors.append(
                            _('El apellido del dorsal %(jersey)s es demasiado largo.') % {'jersey': jersey}
                        )
                        continue
                    person = Person(first_name='', last_name=last_name, is_provisional=True)
                    person.save()
                    action = 'created'

                # Reutilizar una ficha de otro club equivale a adoptarla.
                person.enroll(tenant)
                PlayerRole.objects.create(
                    person=person,
                    identity=identity,
                    season=season,
                    jersey_number=jersey,
                    is_active=True,
                )
        except IntegrityError:
            errors.append(
                _('No se ha podido asignar el dorsal %(jersey)s: ya está ocupado o la ficha ya juega en este equipo.')
                % {'jersey': jersey}
            )
        else:
            # Solo cuenta la fila que se ha confirmado entera.
            if action == 'created':
                created += 1
            elif action == 'reused':
                reused += 1

    if created or reused:
        relink_orphan_lineups()
    return {'created': created, 'reused': reused, 'errors': errors}
