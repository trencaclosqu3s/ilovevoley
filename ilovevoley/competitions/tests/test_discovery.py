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


HISTORICAL_MENU = """
<a data-toggle="collapse" data-parent="#accordion" href="#1" aria-expanded="true" aria-controls="1" >
  INSULAR ESCOLAR MALLORCA
</a>
<a data-toggle="collapse" data-parent="#accordion" href="#100" aria-expanded="true" aria-controls="100" class="category">ALEVIN MASCULINO 4X4 <i class="fa fa-angle-down"></i> </a>
<p class="fase"><i class="fa fa-angle-right"></i> <a href="clasificaciones?id=8020&desp=1001">Liga Regular </a>
<a data-toggle="collapse" data-parent="#accordion" href="#101" aria-expanded="true" aria-controls="101" class="category">BENJAMIN MASCULINO <i class="fa fa-angle-down"></i> </a>
<p class="fase"><i class="fa fa-angle-right"></i> <a href="clasificaciones?id=8090&desp=1002">Liga Regular </a>
"""


def test_parse_menu_keeps_section_category_and_phase():
    assert discovery.parse_menu(MENU) == [
        {'section': 'INSULAR ESCOLAR MALLORCA', 'category_label': 'ALEVIN MASCULINO 4X4',
         'phase_label': 'Liga Regular', 'federation_id': '8020'},
        {'section': 'INSULAR ESCOLAR MALLORCA', 'category_label': 'Categoria unificada',
         'phase_label': 'Liga Regular', 'federation_id': '8095'},
    ]


def test_parse_menu_reads_phases_split_in_groups():
    # Con grupos el enlace lleva title= e icono; antes la regex los descartaba (ligas sin descubrir)
    menu = '''
<a data-toggle="collapse" data-parent="#accordion" href="#1" aria-expanded="true" aria-controls="1" >INSULAR ESCOLAR MALLORCA</a>
<a data-toggle="collapse" data-parent="#accordion" href="#305" aria-expanded="true" aria-controls="305" class="category">Infantil Masculina <i class="fa fa-angle-down"></i> </a>
<p class="fase">Liga Regular</p>
<ul><li><a href="clasificaciones?id=7998&desp=30545" title="Competición"><i class="fa fa-angle-right"></i> GRUP A</a></li>
<li><a href="eliminatoria?id=8163&desp=30546" title="Competición"><i class="fa fa-angle-right"></i> 5è-6è</a></li>
<li><a href="clasificaciones?id=7999&desp=30545" title="Competición"><i class="fa fa-angle-right"></i> GRUP B</a></li></ul>
'''
    assert [(r['federation_id'], r['phase_label']) for r in discovery.parse_menu(menu)] == [
        ('7998', 'Liga Regular - GRUP A'), ('7999', 'Liga Regular - GRUP B'),
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
def test_approve_links_league_already_created_for_same_federation_id():
    season = Season.objects.resolve('2023-24')
    existing = League.objects.create(name='Manual', federation_id='4472', season=season)
    candidate = LeagueCandidate.objects.create(
        federation_id='4472', season=season, category_label='Infantil Masculina', phase_label='Liga Regular',
    )
    assert candidate.approve() == existing
    candidate.refresh_from_db()
    assert (candidate.status, candidate.league) == ('approved', existing)
    assert League.objects.filter(federation_id='4472').count() == 1


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
def test_task_emails_technical_recipients_only_when_there_are_new_candidates(settings):
    from django.contrib.auth import get_user_model

    from ilovevoley.competitions.tasks import discover_leagues_task

    get_user_model().objects.create_superuser('root', 'root@example.com', 'x')
    settings.TECHNICAL_ALERT_EMAILS = ['tech@example.com']
    season = Season.objects.resolve('2026-27')
    candidate = LeagueCandidate.objects.create(federation_id='1', season=season, category_label='ALEVIN MASCULINO 4X4')
    with mock.patch.object(discovery, 'discover', side_effect=[[], [candidate]]), \
            mock.patch.object(discovery, 'discover_seasonal_beach', return_value=[]), \
            mock.patch('ilovevoley.core.email_utils.send_notification_email') as send:
        assert discover_leagues_task() == 0
        send.assert_not_called()
        assert discover_leagues_task() == 1
    kwargs = send.call_args.kwargs
    assert kwargs['subject']()
    assert kwargs['recipient_list'] == ['tech@example.com']  # no a los superusers
    assert kwargs['context']['admin_url'].endswith('/leaguecandidate/?status__exact=pending')


@pytest.mark.django_db
def test_task_aggregates_indoor_and_beach_candidates():
    from ilovevoley.competitions.tasks import discover_leagues_task

    season = Season.objects.resolve('2026-27')
    season.is_current = True
    season.save()
    cand1 = LeagueCandidate.objects.create(federation_id='101', season=season, category_label='ALEVIN')
    cand2 = LeagueCandidate.objects.create(federation_id='102', season=season, category_label='INFANTIL PLAYA', modality='beach')

    with mock.patch.object(discovery, 'discover', return_value=[cand1]), \
            mock.patch.object(discovery, 'discover_seasonal_beach', return_value=[cand2]), \
            mock.patch('ilovevoley.core.email_utils.send_notification_email') as send:
        assert discover_leagues_task() == 2
        send.assert_called_once()
        assert send.call_args.kwargs['context']['count'] == 2


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


def test_is_base_category_matches_only_base_keywords():
    assert discovery.is_base_category('ALEVIN MASCULINO 4X4')
    assert discovery.is_base_category('Cadete Femenino')
    assert discovery.is_base_category('ALEVIN MIXTO')  # sin género claro también vale: decide el superuser
    assert not discovery.is_base_category('BENJAMIN MASCULINO')
    assert not discovery.is_base_category('SENIOR MASCULINO')
    assert not discovery.is_base_category('JUNIOR FEMENINO')


@pytest.mark.django_db
def test_discover_historical_proposes_pending_candidates_without_creating_leagues():
    season = Season.objects.resolve('2023-24')
    alevin = Category.objects.create(name='Alevín Masculino', gender='male')
    Organization.objects.create(slug='sj', name='SJ', club_team_names={'a': 'CLUB TEST'})
    with mock.patch.object(discovery, 'fetch_menu', return_value=HISTORICAL_MENU), \
            mock.patch.object(discovery, 'fetch_team_names', return_value=['CLUB TEST A']):
        created = discovery.discover_historical([season])

    # Solo la candidata de categoría base; benjamín queda fuera
    assert [candidate.federation_id for candidate in created] == ['8020']
    candidate = created[0]
    assert candidate.status == 'pending'
    assert candidate.is_historical is True
    assert candidate.season == season
    assert candidate.category == alevin
    assert candidate.matched_teams == {'sj': ['CLUB TEST A']}
    assert League.objects.count() == 0  # el superuser decide en la cola


@pytest.mark.django_db
def test_approve_historical_candidate_creates_inactive_historical_league():
    season = Season.objects.resolve('2023-24')
    candidate = LeagueCandidate.objects.create(
        federation_id='8020', season=season, category_label='ALEVIN MASCULINO 4X4',
        phase_label='Liga Regular', is_historical=True,
    )
    league = candidate.approve()
    assert (league.visibility_type, league.is_historical, league.is_active) == ('historical', True, False)


@pytest.mark.django_db
def test_discover_historical_skips_known_leagues_and_candidates_without_colliding():
    season = Season.objects.resolve('2023-24')
    Organization.objects.create(slug='sj', name='SJ', club_team_names={'a': 'SANT JOSEP'})
    current = League.objects.create(name='Alevín vigente', federation_id='8020', season=season)
    LeagueCandidate.objects.create(federation_id='8090', season=season, category_label='BENJAMIN')
    with mock.patch.object(discovery, 'fetch_menu', return_value=HISTORICAL_MENU), \
            mock.patch.object(discovery, 'fetch_team_names', return_value=['CV SANT JOSEP A']):
        created = discovery.discover_historical([season])

    assert created == []
    current.refresh_from_db()
    assert (current.visibility_type, current.is_historical) == ('main', False)
    assert League.objects.filter(federation_id='8020').count() == 1


@pytest.mark.django_db
def test_command_windows_previous_seasons_and_leaves_candidates_pending():
    from ilovevoley.competitions.management.commands.discover_historical_leagues import Command

    root = Season.objects.resolve('2026-27')
    root.is_current = True
    root.save()
    Organization.objects.create(slug='sj', name='SJ', club_team_names={'a': 'CLUB TEST'})
    Category.objects.create(name='Alevín Masculino', gender='male')

    def menu(temp, session):
        return HISTORICAL_MENU.replace('8020', f'80{temp}')

    with mock.patch.object(discovery, 'fetch_menu', side_effect=menu), \
            mock.patch.object(discovery, 'fetch_team_names', return_value=['CLUB TEST A']):
        Command().handle(seasons=3, season=None)

    assert sorted(LeagueCandidate.objects.values_list('season__name', flat=True)) == ['2023-24', '2024-25', '2025-26']
    assert LeagueCandidate.objects.filter(is_historical=True, status='pending').count() == 3
    assert League.objects.count() == 0


@pytest.mark.django_db
def test_scrape_historical_task_only_touches_historical_leagues():
    from ilovevoley.competitions.tasks import scrape_historical_leagues_task

    season = Season.objects.resolve('2023-24')
    first = League.objects.create(
        name='Histórica 1', federation_id='H1', season=season,
        visibility_type='historical', is_historical=True, is_active=False,
    )
    second = League.objects.create(
        name='Histórica 2', federation_id='H2', season=season,
        visibility_type='historical', is_historical=True, is_active=False,
    )
    active = League.objects.create(name='Activa', federation_id='A1', season=season)
    with mock.patch('ilovevoley.videos.scraping.FederationScraper') as scraper_cls:
        scraper_cls.return_value.scrape_all_endpoints.return_value = {}
        scraper_cls.return_value.scrape_all_results_rounds.return_value = {'total_matches': 4}
        summary = scrape_historical_leagues_task([first.pk, second.pk, active.pk], delay=0)

    assert {item['league_id'] for item in summary} == {first.pk, second.pk}
    assert all(item['matches'] == 4 for item in summary)
    assert {call.args[0].pk for call in scraper_cls.call_args_list} == {first.pk, second.pk}


@pytest.mark.django_db
def test_discover_historical_button_is_superuser_only(client):
    from django.contrib.auth import get_user_model
    from django.urls import reverse

    users = get_user_model().objects
    staff = users.create_user('staff', 'staff@example.com', 'x', is_staff=True)
    root = users.create_superuser('root', 'root@example.com', 'x')
    url = reverse('admin:competitions_leaguecandidate_discover_historical_now')
    with mock.patch('ilovevoley.competitions.tasks.discover_historical_leagues_task.delay') as delay:
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


@pytest.mark.django_db
def test_candidate_approve_beach_is_admin_only():
    season = Season.objects.resolve('2026-27')
    candidate = LeagueCandidate.objects.create(
        federation_id='99991',
        season=season,
        section='VOLEYPLAYA',
        category_label='INFANTIL MASCULINA PLAYA',
        phase_label='Campeonato de Baleares - GRUP A',
        modality='beach',
        is_historical=False,
    )
    league = candidate.approve()
    assert league.modality == 'beach'
    assert league.visibility_type == 'reference'
    assert league.should_show_in_app is False
    assert league.match_format == 'tournament_3sets'


@pytest.mark.django_db
def test_candidate_approve_indoor_keeps_main_and_standard():
    season = Season.objects.resolve('2026-27')
    candidate = LeagueCandidate.objects.create(
        federation_id='99992',
        season=season,
        section='INSULAR',
        category_label='INFANTIL MASCULINO',
        phase_label='Liga Regular',
        modality='indoor',
        is_historical=False,
    )
    league = candidate.approve()
    assert league.modality == 'indoor'
    assert league.visibility_type == 'main'
    assert league.should_show_in_app is True
    assert league.match_format == 'standard'


def test_detect_modality():
    from ilovevoley.competitions.services.discovery import detect_modality
    assert detect_modality('VOLEYPLAYA', 'INFANTIL MASCULINA PLAYA', 'GRUP A') == 'beach'
    assert detect_modality('AUTONOMICA', 'INFANTIL PLATJA', '') == 'beach'
    assert detect_modality('INSULAR', 'INFANTIL MASCULINO', 'Liga Regular') == 'indoor'


def test_fetch_team_names_calendar_fallback(monkeypatch):
    from ilovevoley.competitions.services import discovery

    # Standings returns empty table
    monkeypatch.setattr(discovery, 'fetch_standings_html', lambda fid, session: "<table><tr><th>Equipo</th></tr></table>")
    # Calendar returns match rows with teams
    calendar_html = (
        "<table class='calendario-completo'>"
        "<tr><td>CV SANT JOSEP LILA</td><td>CV MAYURQA</td><td><strong>07/06/2025<br>17:00</strong></td></tr>"
        "<tr><td>PÒRTOL A</td><td>Descansa</td><td><strong>07/06/2025<br>17:30</strong></td></tr>"
        "</table>"
    )
    monkeypatch.setattr(discovery, 'fetch_calendar_html', lambda fid, session: calendar_html)

    teams = discovery.fetch_team_names('7932')
    assert 'CV SANT JOSEP LILA' in teams
    assert 'CV MAYURQA' in teams
    assert 'PÒRTOL A' in teams
    assert 'Descansa' not in teams


@pytest.mark.django_db
def test_discover_seasonal_beach(monkeypatch):
    from ilovevoley.competitions.services import discovery
    season = Season.objects.resolve('2024-25')
    Organization.objects.update_or_create(slug='santjosep', defaults={'name': 'Sant Josep', 'club_team_names': {'base': 'CV SANT JOSEP'}})

    sample_json = {
        "categorias": [{
            "nombre": "INFANTIL MASCULINA PLAYA",
            "competiciones": [{
                "nombre": "VOLEYPLAYA",
                "fases": [{
                    "nombre": "Campeonato de Baleares",
                    "grupos": [{
                        "id": "7933",
                        "nombre": "GRUP B",
                        "partidos": [
                            {"ELOCAL": "CV SANT JOSEP", "EVISITANTE": "CV ARTÀ"},
                            {"ELOCAL": "PÒRTOL B", "EVISITANTE": "CV SANT JOSEP"}
                        ]
                    }]
                }]
            }]
        }]
    }
    monkeypatch.setattr(discovery, 'fetch_desglose_json', lambda fini, ffin, session: sample_json)

    candidates = discovery.discover_seasonal_beach(season)
    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.federation_id == '7933'
    assert cand.modality == 'beach'
    assert cand.section == 'VOLEYPLAYA'
    assert cand.matched_teams == {'santjosep': ['CV SANT JOSEP']}
    assert cand.is_historical is True


@pytest.mark.django_db
def test_discover_leagues_command_seasonal(monkeypatch):
    from io import StringIO
    from django.core.management import call_command

    season = Season.objects.resolve('2024-25')
    called = []

    def mock_discover_seasonal(s, fini=None, ffin=None):
        called.append((s, fini, ffin))
        return []

    monkeypatch.setattr(
        'ilovevoley.competitions.management.commands.discover_leagues.discover_seasonal_beach',
        mock_discover_seasonal,
    )
    out = StringIO()
    call_command('discover_leagues', '--season', '2024-25', '--seasonal', '--date-range', '01/06/2025', '31/08/2025', stdout=out)
    assert len(called) == 1
    assert called[0] == (season, '01/06/2025', '31/08/2025')
    assert '0 candidatas nuevas en 2024-25' in out.getvalue()


@pytest.mark.django_db
def test_scrape_historical_leagues_beach_command(monkeypatch):
    """Protege la configuración y creación de ligas de playa vía scrape_historical_leagues."""
    from io import StringIO
    from django.core.management import call_command
    from ilovevoley.videos.management.commands.scrape_historical_leagues import Command

    monkeypatch.setattr(Command, 'perform_scraping', lambda self, league, options: None)
    out = StringIO()
    call_command(
        'scrape_historical_leagues',
        '--league-id', '7932',
        '--league-name', 'INFANTIL MASCULINA PLAYA - Grup A',
        '--season', '2024-25',
        '--modality', 'beach',
        '--match-format', 'tournament_3sets',
        stdout=out,
    )
    league = League.objects.get(federation_id='7932')
    assert league.modality == 'beach'
    assert league.match_format == 'tournament_3sets'
    assert league.visibility_type == 'historical'
    assert league.is_reference_league is True
    assert league.should_show_in_app is False
