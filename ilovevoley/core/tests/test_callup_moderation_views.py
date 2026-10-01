import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from ilovevoley.core.models import Season, Organization
from ilovevoley.users.models import Membership
from ilovevoley.rosters.models import Person
from ilovevoley.competitions.models import FederationCallUp, CallUpPlayer

User = get_user_model()


@pytest.mark.django_db
def test_moderation_panel_shows_pending_callups_for_manager(client, settings):
    settings.ALLOWED_HOSTS = ['sant-josep.ilovevoley.es', 'localhost', '127.0.0.1']
    org = Organization.objects.create(name='Sant Josep', slug='sant-josep')
    manager = User.objects.create_user(username='manager', email='mgr@example.com', password='pwd')
    Membership.objects.create(user=manager, organization=org, role='manager', is_approved=True)

    season = Season.objects.create(name='2025-26', start_year=2025, end_year=2026, is_current=True)
    person = Person.objects.create(first_name='Lluc', last_name='Riera', organization=org)
    callup = FederationCallUp.objects.create(season=season, title='Convocatoria 1', source_url='1.pdf')
    player = CallUpPlayer.objects.create(
        callup=callup, organization=org, person=person, match_status='suspected',
        raw_first_name='LLUC', raw_last_name='RIERA', raw_club='CV SANT JOSEP'
    )

    client.login(username='manager', password='pwd')
    response = client.get(reverse('core:moderation_panel'), HTTP_HOST=f"{org.slug}.ilovevoley.es")
    assert response.status_code == 200
    assert player in response.context['pending_callups']
    assert response.context['pending_callups_count'] == 1


@pytest.mark.django_db
def test_confirm_callup_player_api(client, settings):
    settings.ALLOWED_HOSTS = ['sant-josep.ilovevoley.es', 'localhost', '127.0.0.1']
    org = Organization.objects.create(name='Sant Josep', slug='sant-josep')
    manager = User.objects.create_user(username='manager', email='mgr@example.com', password='pwd')
    Membership.objects.create(user=manager, organization=org, role='manager', is_approved=True)
    season = Season.objects.create(name='2025-26', start_year=2025, end_year=2026, is_current=True)
    callup = FederationCallUp.objects.create(season=season, title='Convocatoria 1', source_url='1.pdf')
    player = CallUpPlayer.objects.create(callup=callup, organization=org, match_status='suspected')

    client.login(username='manager', password='pwd')
    url = reverse('core:confirm_callup_api', kwargs={'player_id': player.id})
    resp = client.post(url, HTTP_HOST=f"{org.slug}.ilovevoley.es")
    assert resp.status_code == 200
    assert resp.json()['success'] is True
    player.refresh_from_db()
    assert player.match_status == 'confirmed'
    assert player.reviewed_by == manager


@pytest.mark.django_db
def test_reject_callup_player_api(client, settings):
    settings.ALLOWED_HOSTS = ['sant-josep.ilovevoley.es', 'localhost', '127.0.0.1']
    org = Organization.objects.create(name='Sant Josep', slug='sant-josep')
    manager = User.objects.create_user(username='manager', email='mgr@example.com', password='pwd')
    Membership.objects.create(user=manager, organization=org, role='manager', is_approved=True)
    season = Season.objects.create(name='2025-26', start_year=2025, end_year=2026, is_current=True)
    callup = FederationCallUp.objects.create(season=season, title='Convocatoria 1', source_url='1.pdf')
    player = CallUpPlayer.objects.create(callup=callup, organization=org, match_status='suspected')

    client.login(username='manager', password='pwd')
    url = reverse('core:reject_callup_api', kwargs={'player_id': player.id})
    resp = client.post(url, HTTP_HOST=f"{org.slug}.ilovevoley.es")
    assert resp.status_code == 200
    assert resp.json()['success'] is True
    player.refresh_from_db()
    assert player.match_status == 'rejected'
    assert player.reviewed_by == manager
