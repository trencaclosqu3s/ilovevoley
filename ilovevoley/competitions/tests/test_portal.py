# ilovevoley/competitions/tests/test_portal.py
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
