from unittest.mock import patch

from django.contrib import admin as django_admin
from django.test import TestCase
from django.utils import timezone

from ilovevoley.competitions.admin.competitions import LeagueAdmin, MatchAdmin
from ilovevoley.competitions.models import League, Match
from ilovevoley.core.models import Organization
from ilovevoley.teams.models import Club, Team


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
        from ilovevoley.competitions.models import MatchChangeLog
        request = self.factory.post('/admin/')
        request.user = self.user
        request._messages = []

        self.admin.message_user = lambda req, msg: None
        self.admin.mark_as_reviewed(request, MatchChangeLog.objects.filter(id__in=[self.log1.id, self.log2.id]))

        self.log1.refresh_from_db()
        self.log2.refresh_from_db()
        self.assertTrue(self.log1.reviewed)
        self.assertTrue(self.log2.reviewed)
        self.assertEqual(self.log1.reviewed_by, self.user)
        self.assertIsNotNone(self.log1.reviewed_at)



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
