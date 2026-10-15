import logging

from celery import shared_task
from django.contrib.auth import get_user_model
from django.db import transaction
from django.urls import reverse
from django.utils.translation import gettext as _

from ilovevoley.competitions.models import League
from ilovevoley.core import narrative
from ilovevoley.core.email_utils import send_notification_email
from ilovevoley.core.i18n import push_message
from ilovevoley.core.models import Season
from ilovevoley.core.tenant_utils import build_absolute_url
from ilovevoley.rosters.models import Person, PersonLinkRequest, SeasonWrapped
from ilovevoley.rosters.season_wrapped import (
    NARRATIVE_LANGUAGES,
    NARRATIVE_MAX_CHARS,
    build_wrapped_facts,
    build_wrapped_stats,
    season_organization,
)
from ilovevoley.users.tasks import notify_web_push_organization_task

logger = logging.getLogger(__name__)


def _notify(person, season, organization):
    from ilovevoley.content.services import tagging_push_audience

    player_id, parent_ids = tagging_push_audience(person)
    user_ids = ({player_id} if player_id else set()) | set(parent_ids)
    if not user_ids:
        return
    path = reverse('rosters:season_wrapped_page', args=[person.id]) + f'?season={season.id}'
    name, season_name = person.full_name, season.name

    def build():
        return (
            _('¡Ya está disponible el Wrapped de %(name)s!') % {'name': name},
            _('Mira cómo ha sido la temporada %(season)s.') % {'season': season_name},
        )

    notify_web_push_organization_task.delay(
        organization_id=organization.id, user_ids=list(user_ids), **push_message(build), url=path,
    )
    send_notification_email(
        subject=lambda: _('Ya está disponible el Wrapped de %(name)s') % {'name': name},
        template_name='emails/season_wrapped.html',
        context={'name': name, 'season': season_name, 'site_name': organization.name,
                 'url': build_absolute_url(path, tenant=organization)},
        recipient_list=list(get_user_model().objects.filter(pk__in=user_ids).exclude(email='')
                            .values_list('email', flat=True)),
    )


@shared_task(name='generate_season_wrappeds')
def generate_season_wrappeds_task(season_id, notify=True, no_notify=False):
    """Cierre de temporada (#458, #506): congela el Wrapped de cada jugador y avisa a su familia.

    Idempotente: ``get_or_create`` por (persona, temporada, modalidad); solo se avisa a quien
    recibe una fila nueva. Una corrección de acta posterior exige borrar la fila y relanzar.
    ``notify=False`` o ``no_notify=True`` permite generar wrappeds de prueba sin enviar notificaciones.
    """
    season = Season.objects.filter(pk=season_id).first()
    if season is None:
        return 0
    should_notify = notify and not no_notify
    created = 0
    people = Person.objects.filter(player_roles__season=season).distinct()
    for person in people:
        person_created = False
        for modality, _label in League.MODALITY_CHOICES:
            stats = build_wrapped_stats(person, season, modality)
            if stats is None:
                continue
            _row, was_created = SeasonWrapped.objects.get_or_create(
                person=person, season=season, modality=modality, defaults={'stats': stats},
            )
            created += was_created
            person_created = person_created or was_created
        if person_created and should_notify:
            organization = season_organization(person, season)
            if organization:
                _notify(person, season, organization)
    return created


def _store_narrative(row, language, text):
    """Añade solo la clave del idioma a ``stats['narrative']``, sin pisar el resto del JSON."""
    with transaction.atomic():
        fresh = SeasonWrapped.objects.select_for_update().get(pk=row.pk)
        fresh.stats.setdefault('narrative', {})[language] = text
        fresh.save(update_fields=['stats'])
    row.stats = fresh.stats


@shared_task(name='redact_pending_wrapped_narratives')
def redact_pending_wrapped_narratives_task(limit=20, season_id=None):
    """Redacta con LLM (#551) los idiomas que faltan en ``stats['narrative']`` de cada Wrapped.

    Idempotente: un idioma presente (texto o ``None`` por descarte definitivo, D2) no se
    reintenta; uno con fallo transitorio no se escribe y queda pendiente. Corta la tanda al
    primer fallo de la API. Devuelve cuántos textos ha guardado.
    """
    if not narrative.is_enabled():
        return 0
    rows = SeasonWrapped.objects.filter(stats__matches__gt=0).select_related('person', 'season')
    if season_id:
        rows = rows.filter(season_id=season_id)
    saved = 0
    # Recorre todas las filas cada noche (la clave por idioma no se filtra bien en BD con
    # null); si crecen a decenas de miles, habrá que filtrar en la consulta.
    for row in rows.order_by('-season__start_year', '-id').iterator():
        missing = [lang for lang in NARRATIVE_LANGUAGES if lang not in (row.stats.get('narrative') or {})]
        if not missing:
            continue
        facts = build_wrapped_facts(row)
        for language in missing:
            if saved >= limit:
                return saved
            try:
                text = narrative.redact(facts, locale=language, max_chars=NARRATIVE_MAX_CHARS, style='wrapped')
            except narrative.NarrativeDiscarded:
                text = None
            except narrative.NarrativeTransientError as e:
                logger.warning('Redacción del Wrapped interrumpida, se retoma la noche siguiente: %s', e)
                return saved
            except narrative.NarrativeError as e:
                logger.error('Redacción del Wrapped: error de la API: %s', e)
                return saved
            _store_narrative(row, language, text)
            saved += 1
    return saved


@shared_task(name='notify_person_link_result')
def notify_person_link_result_task(link_request_id, approved, site_url=None, site_name=None):
    """Avisa al usuario de la resolución de su solicitud de vínculo (#531).

    Push a sus dispositivos del club y email, ambos en su idioma. La solicitud
    se lee de base de datos porque la tarea corre fuera del ciclo de petición.
    """
    try:
        link_request = PersonLinkRequest.objects.select_related(
            'person', 'user', 'organization',
        ).get(pk=link_request_id)
    except PersonLinkRequest.DoesNotExist:
        return False

    user = link_request.user
    organization = link_request.organization
    person_name = link_request.person.full_name
    resolved_site_name = site_name or organization.name
    profile_path = reverse('rosters:my_profile')

    def build():
        if approved:
            return (
                _('Vínculo aprobado'),
                _('Tu cuenta ya está vinculada con la ficha de %(name)s.') % {'name': person_name},
            )
        return (
            _('Solicitud de vínculo revisada'),
            _('No hemos podido vincular tu cuenta con la ficha de %(name)s.') % {'name': person_name},
        )

    notify_web_push_organization_task.delay(
        organization_id=organization.id,
        user_ids=[user.id],
        url=profile_path,
        **push_message(build),
    )

    if user.email:
        send_notification_email(
            subject=(
                (lambda: _('Tu vínculo con %(name)s ha sido aprobado') % {'name': person_name})
                if approved
                else (lambda: _('Actualización de tu solicitud de vínculo'))
            ),
            template_name=(
                'emails/person_link_approved.html' if approved else 'emails/person_link_rejected.html'
            ),
            context={
                'user': user,
                'person_name': person_name,
                'site_name': resolved_site_name,
                'site_url': site_url or build_absolute_url(profile_path, tenant=organization),
            },
            recipient_list=[user.email],
        )
    return True
