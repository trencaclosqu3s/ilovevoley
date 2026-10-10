from celery import shared_task
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils.translation import gettext as _

from ilovevoley.competitions.models import League
from ilovevoley.core.email_utils import send_notification_email
from ilovevoley.core.i18n import push_message
from ilovevoley.core.models import Season
from ilovevoley.core.tenant_utils import build_absolute_url
from ilovevoley.rosters.models import Person, SeasonWrapped
from ilovevoley.rosters.season_wrapped import build_wrapped_stats, season_organization
from ilovevoley.users.tasks import notify_web_push_organization_task


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
def generate_season_wrappeds_task(season_id):
    """Cierre de temporada (#458): congela el Wrapped de cada jugador y avisa a su familia.

    Idempotente: ``get_or_create`` por (persona, temporada, modalidad); solo se avisa a quien
    recibe una fila nueva. Una corrección de acta posterior exige borrar la fila y relanzar.
    """
    season = Season.objects.filter(pk=season_id).first()
    if season is None:
        return 0
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
        if person_created:
            organization = season_organization(person, season)
            if organization:
                _notify(person, season, organization)
    return created
