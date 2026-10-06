from unittest import mock

import pytest

from ilovevoley.competitions.models import League, LeagueCandidate
from ilovevoley.competitions.services import discovery
from ilovevoley.core.models import Category, Organization, Season

MENU = """
<a data-toggle="collapse" data-parent="#accordion" href="#1" aria-expanded="true" aria-controls="1" >
  INSULAR ESCOLAR MALLORCA
</a>
<a data-toggle="collapse" data-parent="#accordion" href="#100" aria-expanded="true" aria-controls="100" class="category">ALEVIN MASCULINO 4X4 <i class="fa fa-angle-down"></i> </a>
<p class="fase"><i class="fa fa-angle-right"></i> <a href="clasificaciones?id=8020&desp=1001">Liga Regular </a>
<a data-toggle="collapse" data-parent="#accordion" href="#101" aria-expanded="true" aria-controls="101" class="category">Categoria unificada <i class="fa fa-angle-down"></i> </a>
<p class="fase"><i class="fa fa-angle-right"></i> <a href="clasificaciones?id=8095&desp=1002">Liga Regular </a>
"""


def test_parse_menu_keeps_section_category_and_phase():
    assert discovery.parse_menu(MENU) == [
        {'section': 'INSULAR ESCOLAR MALLORCA', 'category_label': 'ALEVIN MASCULINO 4X4',
         'phase_label': 'Liga Regular', 'federation_id': '8020'},
        {'section': 'INSULAR ESCOLAR MALLORCA', 'category_label': 'Categoria unificada',
         'phase_label': 'Liga Regular', 'federation_id': '8095'},
    ]


@pytest.mark.django_db
def test_detect_category_needs_clear_keyword_and_gender():
    alevin = Category.objects.create(name='Alevín Masculino', gender='male')
    Category.objects.create(name='Alevín Femenino', gender='female')
    assert discovery.detect_category('ALEVIN MASCULINO 4X4') == alevin
    assert discovery.detect_category('ALEVIN') is None
    assert discovery.detect_category('Categoria unificada') is None


@pytest.mark.django_db
def test_matching_tenants_never_falls_back_to_default_club():
    ours = Organization.objects.create(slug='sj', name='SJ', club_team_names={'Alevin': 'SANT JOSEP'})
    no_names = Organization.objects.create(slug='other', name='Other')
    result = discovery.matching_tenants(['CV SANT JOSEP A', 'CV MATARO'], [ours, no_names])
    assert result == {ours: ['CV SANT JOSEP A']}


@pytest.mark.django_db
def test_discover_skips_known_and_leagues_without_our_teams():
    season = Season.objects.resolve('2026-27')
    Organization.objects.create(slug='sj', name='SJ', club_team_names={'a': 'SANT JOSEP'})
    League.objects.create(name='Ya existe', federation_id='8095', season=season)
    teams = {'8020': ['CV SANT JOSEP A']}
    with mock.patch.object(discovery, 'fetch_menu', return_value=MENU), \
            mock.patch.object(discovery, 'fetch_team_names', side_effect=lambda i, s: teams.get(i, ['OTRO'])) as fetch:
        created = discovery.discover(season)
        assert [c.federation_id for c in created] == ['8020']
        assert discovery.discover(season) == []  # idempotente: no la vuelve a proponer
    assert 8095 not in [int(c.args[0]) for c in fetch.call_args_list]


@pytest.mark.django_db
def test_approve_creates_league_with_endpoints_once():
    season = Season.objects.resolve('2026-27')
    category = Category.objects.create(name='Alevín Masculino', gender='male')
    candidate = LeagueCandidate.objects.create(
        federation_id='8020', season=season, category_label='ALEVIN MASCULINO 4X4',
        phase_label='Liga Regular', category=category,
    )
    league = candidate.approve()
    assert candidate.approve() == league
    assert League.objects.filter(federation_id='8020').count() == 1
    assert league.endpoints.count() == 3
    assert list(league.categories.all()) == [category]


@pytest.mark.django_db
def test_discover_suggests_parent_by_category_across_sections():
    season = Season.objects.resolve('2026-27')
    Organization.objects.create(slug='sj', name='SJ', club_team_names={'a': 'SANT JOSEP'})
    base = dict(season=season, category_label='ALEVIN MASCULINO 4X4', phase_label='Liga Regular')
    first = LeagueCandidate.objects.create(federation_id='1', section='INSULAR ESCOLAR MALLORCA', **base).approve()
    menu = MENU.replace('INSULAR ESCOLAR MALLORCA', 'COPA NADAL')
    with mock.patch.object(discovery, 'fetch_menu', return_value=menu), \
            mock.patch.object(discovery, 'fetch_team_names', return_value=['CV SANT JOSEP A']):
        copa = discovery.discover(season)[0]
    assert copa.parent_league == first
    league = copa.approve()
    assert (league.parent_league, league.phase_name, league.competition_type) == (first, 'Liga Regular', 'cup')


@pytest.mark.django_db
def test_discover_survives_failed_standings_and_remembers_foreign_leagues():
    season = Season.objects.resolve('2026-27')
    Organization.objects.create(slug='sj', name='SJ', club_team_names={'a': 'SANT JOSEP', 'blank': ' ', 'none': None})
    menu = MENU + '<p class="fase"><a href="clasificaciones?id=9000&desp=1">Liga Regular </a>'

    def teams(federation_id, session):
        if federation_id == '8020':
            raise discovery.requests.ConnectionError
        return {'8095': ['OTRO CLUB'], '9000': []}[federation_id]

    with mock.patch.object(discovery, 'fetch_menu', return_value=menu), \
            mock.patch.object(discovery, 'fetch_team_names', side_effect=teams):
        assert discovery.discover(season) == []
    # Con equipos pero ninguno nuestro: no se vuelve a pedir; caída o vacía: se reintenta
    assert dict(LeagueCandidate.objects.values_list('federation_id', 'status')) == {'8095': 'rejected'}
    assert discovery.discover(None) == []


@pytest.mark.django_db
def test_task_emails_superusers_only_when_there_are_new_candidates():
    from django.contrib.auth import get_user_model

    from ilovevoley.competitions.tasks import discover_leagues_task

    get_user_model().objects.create_superuser('root', 'root@example.com', 'x')
    season = Season.objects.resolve('2026-27')
    candidate = LeagueCandidate.objects.create(federation_id='1', season=season, category_label='ALEVIN MASCULINO 4X4')
    with mock.patch.object(discovery, 'discover', side_effect=[[], [candidate]]), \
            mock.patch('ilovevoley.core.email_utils.send_notification_email') as send:
        assert discover_leagues_task() == 0
        send.assert_not_called()
        assert discover_leagues_task() == 1
    kwargs = send.call_args.kwargs
    assert kwargs['subject']()
    assert kwargs['recipient_list'] == ['root@example.com']
    assert kwargs['context']['admin_url'].endswith('/leaguecandidate/?status__exact=pending')


@pytest.mark.django_db
def test_discover_now_button_is_superuser_only(client):
    from django.contrib.auth import get_user_model
    from django.urls import reverse

    users = get_user_model().objects
    staff = users.create_user('staff', 'staff@example.com', 'x', is_staff=True)
    root = users.create_superuser('root', 'root@example.com', 'x')
    url = reverse('admin:competitions_leaguecandidate_discover_now')
    with mock.patch('ilovevoley.competitions.tasks.discover_leagues_task.delay') as delay:
        client.force_login(staff)
        client.get(url)
        delay.assert_not_called()
        client.force_login(root)
        client.get(url)
        delay.assert_called_once_with()


@pytest.mark.django_db
def test_discover_links_manual_league_so_it_can_be_suggested_as_parent():
    season = Season.objects.resolve('2026-27')
    Organization.objects.create(slug='sj', name='SJ', club_team_names={'a': 'SANT JOSEP'})
    manual = League.objects.create(name='Alevín a mano', federation_id='8020', season=season)
    # Antes de crearla a mano, una pasada la guardó como ajena (rechazada)
    LeagueCandidate.objects.create(federation_id='8020', season=season, status='rejected')
    menu = MENU + MENU.replace('8020', '8999').replace('8095', '8998').replace('INSULAR ESCOLAR MALLORCA', 'COPA NADAL')
    with mock.patch.object(discovery, 'fetch_menu', return_value=menu), \
            mock.patch.object(discovery, 'fetch_team_names', return_value=['CV SANT JOSEP A']):
        created = discovery.discover(season)
    assert manual.candidate.status == 'approved' and manual.candidate.section == 'INSULAR ESCOLAR MALLORCA'
    assert LeagueCandidate.objects.get(federation_id='8999').parent_league == manual
    assert '8020' not in [c.federation_id for c in created]
