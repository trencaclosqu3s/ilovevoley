import pytest
from unittest.mock import patch
from ilovevoley.core.models import Season, Organization
from ilovevoley.rosters.models import Person
from ilovevoley.competitions.models import FederationCallUp, CallUpPlayer
from ilovevoley.competitions.services.notifications import (
    notify_callup_confirmed,
    notify_callup_suspected,
)


@pytest.mark.django_db
@patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
def test_notify_callup_confirmed(mock_task):
    season = Season.objects.create(name='2025-26', start_year=2025, end_year=2026, is_current=True)
    org = Organization.objects.create(name='Sant Josep', slug='sant-josep')
    person = Person.objects.create(first_name='Lluc', last_name='Riera', organization=org)
    callup = FederationCallUp.objects.create(
        season=season, title='Convocatoria 1', source_url='1.pdf', modality='indoor', category_name='Infantil', gender='M'
    )
    player = CallUpPlayer.objects.create(
        callup=callup, organization=org, person=person, match_status='confirmed',
        raw_first_name='LLUC', raw_last_name='RIERA'
    )

    res = notify_callup_confirmed(player)
    assert res is True
    player.refresh_from_db()
    assert player.notification_sent is True
    assert mock_task.called
    kwargs = mock_task.call_args[1]
    assert kwargs['organization_id'] == org.id
    assert 'Convocatoria con la Selección Balear' in kwargs['title']
    assert kwargs['notification_type'] == 'callup_confirmed'

    # Idempotencia: no debe duplicar si ya está enviado
    mock_task.reset_mock()
    res2 = notify_callup_confirmed(player)
    assert res2 is False
    assert not mock_task.called


@pytest.mark.django_db
@patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
def test_notify_callup_suspected(mock_task):
    season = Season.objects.create(name='2025-26', start_year=2025, end_year=2026, is_current=True)
    org = Organization.objects.create(name='Sant Josep', slug='sant-josep')
    person = Person.objects.create(first_name='Lluc', last_name='Riera', organization=org)
    callup = FederationCallUp.objects.create(
        season=season, title='Convocatoria 1', source_url='1.pdf', modality='indoor', category_name='Infantil', gender='M'
    )
    player = CallUpPlayer.objects.create(
        callup=callup, organization=org, person=person, match_status='suspected',
        raw_first_name='LLUC', raw_last_name='RIERA'
    )

    res = notify_callup_suspected(player)
    assert res is True
    player.refresh_from_db()
    assert player.notification_sent is True
    assert mock_task.called
    kwargs = mock_task.call_args[1]
    assert kwargs['organization_id'] == org.id
    assert kwargs['notification_type'] == 'admin_alert'
    assert kwargs['url'] == '/core/moderacion/#convocatorias'

    # Idempotencia
    mock_task.reset_mock()
    res2 = notify_callup_suspected(player)
    assert res2 is False
    assert not mock_task.called
