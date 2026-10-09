# ilovevoley/competitions/tests/test_portal.py
from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ilovevoley.competitions.models import League, Match, Standing
from ilovevoley.competitions.services.public_portal import public_leagues, public_matches
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.teams.models import Club, Team


@override_settings(
    ALLOWED_HOSTS=['ilovevoley.es', 'testclub.ilovevoley.es', 'localhost'],
    TENANT_BASE_DOMAIN='ilovevoley.es',
    SECURE_SSL_REDIRECT=False,
)
class PublicLeaguesCatalogTest(TestCase):
    """Catálogo del portal: temporada + visibilidad (regla de producto #124)."""

    def setUp(self):
        self.current = Season.objects.create(
            name='2026-27', start_year=2026, end_year=2027, is_current=True,
        )
        self.past = Season.objects.create(
            name='2025-26', start_year=2025, end_year=2026, is_current=False,
        )
        self.main = League.objects.create(
            name='Liga Main', federation_id='PORTAL-MAIN',
            season=self.current, visibility_type='main',
            is_our_team_related=False, is_active=True,
        )
        self.historical = League.objects.create(
            name='Liga Hist', federation_id='PORTAL-HIST',
            season=self.past, visibility_type='historical',
            is_historical=True, is_active=False, is_our_team_related=False,
        )
        self.reference = League.objects.create(
            name='Liga Ref', federation_id='PORTAL-REF',
            season=self.current, visibility_type='reference',
            is_our_team_related=True, is_active=True,
        )
        self.friendly = League.objects.create(
            name='Amistosos', federation_id='PORTAL-FRI',
            season=self.current, visibility_type='main',
            competition_type='friendly', is_active=True,
        )

    def test_public_leagues_includes_main_and_historical_for_season(self):
        qs = public_leagues(self.past)
        self.assertIn(self.historical, qs)
        self.assertNotIn(self.main, qs)

    def test_public_leagues_excludes_reference_external_and_friendly(self):
        qs = public_leagues(self.current)
        self.assertIn(self.main, qs)
        self.assertNotIn(self.reference, qs)
        self.assertNotIn(self.friendly, qs)

    def test_public_leagues_does_not_require_our_team_related(self):
        qs = public_leagues(self.current)
        self.assertFalse(self.main.is_our_team_related)
        self.assertIn(self.main, qs)


@override_settings(
    ALLOWED_HOSTS=['ilovevoley.es', 'testclub.ilovevoley.es', 'localhost'],
    TENANT_BASE_DOMAIN='ilovevoley.es',
    SECURE_SSL_REDIRECT=False,
)
class BrandPortalHostTest(TestCase):
    """Portal solo en dominio raíz; en tenant 404 (#124)."""

    def setUp(self):
        self.season = Season.objects.create(
            name='2026-27', start_year=2026, end_year=2027, is_current=True,
        )
        self.past = Season.objects.create(
            name='2025-26', start_year=2025, end_year=2026, is_current=False,
        )
        League.objects.create(
            name='Liga Main', federation_id='PORTAL-HOST-MAIN',
            season=self.season, visibility_type='main', is_active=True,
        )
        League.objects.create(
            name='Liga Pasada', federation_id='PORTAL-HOST-PAST',
            season=self.past, visibility_type='historical', is_active=False,
        )
        club = Club.objects.create(
            official_name='Club Portal Test', federation_id='CLUB-PORTAL',
        )
        Organization.objects.create(
            slug='testclub', name='Test Club Org', club=club, is_active=True,
        )

    def test_anonymous_root_lists_leagues(self):
        response = self.client.get(
            reverse('portal:league_list'), HTTP_HOST='ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Liga Main')
        self.assertNotContains(response, 'Liga Pasada')

    def test_season_param_selects_other_season(self):
        response = self.client.get(
            reverse('portal:league_list'), {'season': self.past.pk},
            HTTP_HOST='ilovevoley.es',
        )
        self.assertContains(response, 'Liga Pasada')
        self.assertNotContains(response, 'Liga Main')

    def test_index_root_ok(self):
        response = self.client.get(reverse('portal:index'), HTTP_HOST='ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Liga Main')

    def test_tenant_host_returns_404(self):
        for name in ('portal:index', 'portal:league_list'):
            with self.subTest(view=name):
                response = self.client.get(
                    reverse(name), HTTP_HOST='testclub.ilovevoley.es',
                )
                self.assertEqual(response.status_code, 404)


@override_settings(
    ALLOWED_HOSTS=['ilovevoley.es', 'testclub.ilovevoley.es', 'localhost'],
    TENANT_BASE_DOMAIN='ilovevoley.es',
    SECURE_SSL_REDIRECT=False,
)
class BrandPortalLeagueViewsTest(TestCase):
    """Detalle, calendario, resultados y clasificación del portal (#124)."""

    def setUp(self):
        self.season = Season.objects.create(
            name='2026-27', start_year=2026, end_year=2027, is_current=True,
        )
        club = Club.objects.create(official_name='Club X', federation_id='CLUB-X')
        self.alpha = Team.objects.create(name='Alpha VC', federation_id='t-alpha', club=club)
        self.beta = Team.objects.create(name='Beta VC', federation_id='t-beta', club=club)
        self.league = League.objects.create(
            name='Liga Main', federation_id='PL-MAIN', season=self.season,
            visibility_type='main', is_active=True,
        )
        self.other = League.objects.create(
            name='Liga Otra', federation_id='PL-OTHER', season=self.season,
            visibility_type='main', is_active=True,
        )
        self.reference = League.objects.create(
            name='Liga Ref', federation_id='PL-REF', season=self.season,
            visibility_type='reference', is_active=True,
        )
        now = timezone.now()
        self.future = Match.objects.create(
            league=self.league, home_team=self.alpha, away_team=self.beta,
            match_date=now + timedelta(days=3), status='scheduled',
            federation_id='PM-FUT',
        )
        self.done = Match.objects.create(
            league=self.league, home_team=self.beta, away_team=self.alpha,
            match_date=now - timedelta(days=3), status='finished',
            home_score=3, away_score=1, federation_id='PM-DONE',
        )
        self.other_future = Match.objects.create(
            league=self.other, home_team=self.alpha, away_team=self.beta,
            match_date=now + timedelta(days=5), status='scheduled',
            federation_id='PM-OTHER',
        )
        Standing.objects.create(
            league=self.league, team=self.alpha, position=2, total_points=3,
        )
        Standing.objects.create(
            league=self.league, team=self.beta, position=1, total_points=10,
        )

    def get(self, name, *args, **params):
        return self.client.get(
            reverse(name, args=args), params, HTTP_HOST='ilovevoley.es',
        )

    def test_league_detail_shows_standings_and_matches(self):
        response = self.get('portal:league_detail', self.league.pk)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Liga Main')
        self.assertContains(response, 'Alpha VC')
        self.assertEqual(
            [s.team for s in response.context['standings']], [self.beta, self.alpha],
        )
        self.assertEqual(list(response.context['upcoming']), [self.future])
        self.assertEqual(list(response.context['recent']), [self.done])

    def test_league_detail_hides_non_public_league(self):
        response = self.get('portal:league_detail', self.reference.pk)
        self.assertEqual(response.status_code, 404)

    def test_league_detail_of_past_season_opens_without_season_param(self):
        past = Season.objects.create(
            name='2025-26', start_year=2025, end_year=2026, is_current=False,
        )
        old = League.objects.create(
            name='Liga Hist', federation_id='PL-HIST', season=past,
            visibility_type='historical', is_active=False,
        )
        response = self.get('portal:league_detail', old.pk)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Liga Hist')

    def test_calendar_lists_only_upcoming_and_filters_by_league(self):
        response = self.get('portal:calendar')
        self.assertEqual(
            set(response.context['matches']), {self.future, self.other_future},
        )
        response = self.get('portal:calendar', league=self.other.pk)
        self.assertEqual(list(response.context['matches']), [self.other_future])

    def test_results_lists_only_finished(self):
        response = self.get('portal:results')
        self.assertEqual(list(response.context['matches']), [self.done])
        self.assertContains(response, '3 - 1')

    def test_standings_requires_league_selection(self):
        response = self.get('portal:standings')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['standings']), 0)
        response = self.get('portal:standings', league=self.league.pk)
        self.assertEqual(response.context['selected_league'], self.league)
        self.assertEqual(len(response.context['standings']), 2)

    def test_standings_rejects_league_outside_catalog(self):
        response = self.get('portal:standings', league=self.reference.pk)
        self.assertEqual(response.status_code, 404)

    def test_tenant_host_returns_404(self):
        for name, args in (
            ('portal:league_detail', (self.league.pk,)),
            ('portal:calendar', ()),
            ('portal:results', ()),
            ('portal:standings', ()),
        ):
            with self.subTest(view=name):
                response = self.client.get(
                    reverse(name, args=args), HTTP_HOST='testclub.ilovevoley.es',
                )
                self.assertEqual(response.status_code, 404)
