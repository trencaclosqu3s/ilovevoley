from unittest.mock import patch

from django.contrib import admin as django_admin
from django.test import TestCase, override_settings
from django.utils import timezone

from ilovevoley.competitions.admin.competitions import (
    LeagueAdmin,
    MatchActaPhotoAdmin,
    MatchAdmin,
)
from ilovevoley.competitions.models import League, Match, MatchActaPhoto
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.teams.models import Club, Team
from ilovevoley.teams.tests.helpers import identity_of


class LeagueRelatedOrganizationsTest(TestCase):
    """La detección FK + string alimenta el aviso de is_our_team_related."""

    @classmethod
    def setUpTestData(cls):
        cls.club = Club.objects.create(federation_id='c-1', official_name='CV SANT JOSEP')
        cls.org = Organization.objects.create(
            slug='test-org', name='Test', club=cls.club, club_team_names={'Senior': 'SANT JOSEP'},
        )

    def setUp(self):
        self.admin = LeagueAdmin(League, django_admin.site)

    def _league_with_team(self, team, fed_id):
        league = League.objects.create(name=f'Lliga {fed_id}', federation_id=fed_id)
        Match.objects.create(league=league, home_team=team, match_date=timezone.now())
        return league

    def test_detects_organization_by_club_fk(self):
        team = Team.objects.create(name='BAR BINI SOLLER', federation_id='t-1', club=self.club)
        league = self._league_with_team(team, 'l-1')
        self.assertIn('test-org', self.admin.related_organizations(league))

    def test_detects_organization_by_orphan_name(self):
        team = Team.objects.create(name='CV SANT JOSEP B', federation_id='t-2', club=None)
        league = self._league_with_team(team, 'l-2')
        self.assertIn('test-org', self.admin.related_organizations(league))

    def test_no_organization_when_unrelated(self):
        team = Team.objects.create(name='CV ALTRES', federation_id='t-3')
        league = self._league_with_team(team, 'l-3')
        self.assertIn('Ninguna', self.admin.related_organizations(league))


class MatchChangeLogAdminTest(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.test import RequestFactory
        from ilovevoley.competitions.admin.competitions import MatchChangeLogAdmin
        from ilovevoley.competitions.models import MatchChangeLog

        User = get_user_model()
        self.user = User.objects.create_superuser(username='admin_user', email='admin@test.com')
        self.factory = RequestFactory()
        self.admin = MatchChangeLogAdmin(MatchChangeLog, django_admin.site)

        club = Club.objects.create(federation_id='c-admin', official_name='CV ADMIN')
        self.org = Organization.objects.create(slug='admin-org', name='Admin Org', club=club)
        team = Team.objects.create(name='ADMIN TEAM', federation_id='t-admin', club=club)
        league = League.objects.create(name='Admin League', federation_id='l-admin')
        self.match = Match.objects.create(league=league, home_team=team, match_date=timezone.now())

        self.log1 = MatchChangeLog.objects.create(
            match=self.match, change_type='datetime', field_name='match_date', old_value='10:00', new_value='12:00'
        )
        self.log2 = MatchChangeLog.objects.create(
            match=self.match, change_type='venue', field_name='venue', old_value='Pista 1', new_value='Pista 2'
        )

    def test_mark_as_reviewed_action(self):
        """La acción de admin crea MatchChangeLogReview por org del partido (#201)."""
        from ilovevoley.competitions.models import MatchChangeLog, MatchChangeLogReview
        request = self.factory.post('/admin/')
        request.user = self.user
        request._messages = []

        self.admin.message_user = lambda req, msg: None
        self.admin.mark_as_reviewed(request, MatchChangeLog.objects.filter(id__in=[self.log1.id, self.log2.id]))

        reviews = MatchChangeLogReview.objects.filter(change_log__in=[self.log1, self.log2])
        self.assertEqual(reviews.count(), 2)
        self.assertTrue(reviews.filter(change_log=self.log1, organization=self.org).exists())
        self.assertTrue(reviews.filter(change_log=self.log2, organization=self.org).exists())
        self.assertEqual(reviews.get(change_log=self.log1).reviewed_by, self.user)
        self.assertIsNotNone(reviews.get(change_log=self.log1).reviewed_at)



class MatchAdminResultNotificationTest(TestCase):
    """#361: el resultado puesto desde el admin fija result_notified_at (ancla del push de fotos)."""

    def setUp(self):
        self.admin = MatchAdmin(Match, django_admin.site)
        self.match = Match.objects.create(
            home_team=Team.objects.create(name='A', federation_id='t-a'),
            away_team=Team.objects.create(name='B', federation_id='t-b'),
            match_date=timezone.now(),
            is_friendly=True,
        )

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_saving_finished_result_sets_anchor_once(self, _push):
        self.match.status, self.match.home_score, self.match.away_score = 'finished', 3, 0
        self.admin.save_model(None, self.match, None, change=True)
        self.match.refresh_from_db()
        first = self.match.result_notified_at
        self.assertIsNotNone(first)

        # Reeditar un partido ya finalizado no reinicia el ancla
        self.match.referee1 = 'Árbitro'
        self.admin.save_model(None, self.match, None, change=True)
        self.match.refresh_from_db()
        self.assertEqual(self.match.result_notified_at, first)


class LeagueHistoricalScrapeActionTest(TestCase):
    """#404: la acción de sincronización histórica encola solo ligas históricas."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory

        self.user = get_user_model().objects.create_superuser(
            username='hist_admin', email='hist@test.com',
        )
        self.factory = RequestFactory()
        self.admin = LeagueAdmin(League, django_admin.site)
        self.FallbackStorage = FallbackStorage

    def _request(self):
        request = self.factory.post('/admin/')
        request.user = self.user
        request.session = {}
        request._messages = self.FallbackStorage(request)
        return request

    def test_warns_without_crashing_when_no_historical_selected(self):
        active = League.objects.create(name='Activa', federation_id='sh-act')
        with patch('ilovevoley.competitions.tasks.scrape_historical_leagues_task.delay') as delay:
            self.admin.scrape_historical(self._request(), League.objects.filter(pk=active.pk))
        delay.assert_not_called()

    def test_enqueues_only_the_historical_selection(self):
        historical = League.objects.create(
            name='Histórica', federation_id='sh-hist',
            visibility_type='historical', is_historical=True, is_active=False,
        )
        active = League.objects.create(name='Activa', federation_id='sh-act2')
        with patch('ilovevoley.competitions.tasks.scrape_historical_leagues_task.delay') as delay:
            self.admin.scrape_historical(
                self._request(), League.objects.filter(pk__in=[historical.pk, active.pk]),
            )
        delay.assert_called_once_with([historical.pk])

    def test_action_dispatched_like_django_does_not_crash(self):
        # #483: get_actions devolvía métodos enlazados y Django, que pasa
        # modeladmin explícito, fallaba con "takes 3 positional arguments but 4 were given".
        historical = League.objects.create(
            name='Histórica', federation_id='sh-hist3',
            visibility_type='historical', is_historical=True, is_active=False,
        )
        request = self._request()
        func, _, _ = self.admin.get_actions(request)['scrape_historical']
        with patch('ilovevoley.competitions.tasks.scrape_historical_leagues_task.delay') as delay:
            func(self.admin, request, League.objects.filter(pk=historical.pk))
        delay.assert_called_once_with([historical.pk])


class MatchActaPhotoRosterLinksTest(TestCase):
    """El atajo del acta a la plantilla debe resolverse en el subdominio del club (#569).

    El admin se sirve en el dominio raíz, donde no hay tenant: una ruta relativa
    dejaría la vista de plantilla sin club.
    """

    @classmethod
    def setUpTestData(cls):
        cls.club = Club.objects.create(federation_id='c-1', official_name='CV SANT JOSEP')
        cls.org = Organization.objects.create(
            slug='club-test-569', name='Club Test 569', club=cls.club,
            club_team_names={'569': 'CLUB TEST 569'}, is_active=True,
        )
        cls.category = Category.objects.create(name='Infantil', is_active=True)
        cls.team = Team.objects.create(
            name='CLUB TEST 569 INFANTIL', category=cls.category, club=cls.club,
            federation_id='t-1', is_active=True,
        )
        identity_of(cls.team)
        cls.rival = Team.objects.create(
            name='RIVAL INFANTIL', category=cls.category,
            club=Club.objects.create(federation_id='c-rival', official_name='Rival'),
            federation_id='t-2', is_active=True,
        )
        cls.season = Season.objects.resolve('2025-26')
        cls.league = League.objects.create(
            name='Lliga Infantil', federation_id='l-1', season=cls.season,
            is_active=True, visibility_type='main', is_our_team_related=True,
        )
        cls.match = Match.objects.create(
            league=cls.league, home_team=cls.team, away_team=cls.rival,
            match_date=timezone.now(), round_number=1, status='finished',
        )
        cls.photo = MatchActaPhoto.objects.create(
            match=cls.match, source_url='https://example.com/acta.jpg',
        )

    def setUp(self):
        self.admin = MatchActaPhotoAdmin(MatchActaPhoto, django_admin.site)

    @override_settings(DEBUG=False, TENANT_BASE_DOMAIN='ilovevoley.es')
    def test_enlaza_con_el_subdominio_del_club_y_omite_al_rival(self):
        html = str(self.admin.roster_from_acta_links(self.photo))

        self.assertIn(
            f'https://club-test-569.ilovevoley.es/teams/equipos/{self.team.id}/plantilla/?season={self.season.pk}',
            html,
        )
        self.assertNotIn('RIVAL', html)
