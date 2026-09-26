from datetime import datetime

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ilovevoley.competitions import calendar_feed as comp_calendar_feed
from ilovevoley.competitions import forms as comp_forms
from ilovevoley.competitions import views as comp_views
from ilovevoley.competitions.models import League, Match, Standing
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.teams.models import Club, Team
from ilovevoley.videos import calendar_feed as vid_calendar_feed
from ilovevoley.videos.forms import competitions as vid_forms_comp
from ilovevoley.videos.views import competitions as vid_views_comp


class CompetitionsReExportCompatibilityTest(TestCase):
    """Verifica que las importaciones históricas desde videos sigan funcionando."""

    def test_views_are_reexported(self):
        self.assertIs(vid_views_comp.league_list, comp_views.league_list)
        self.assertIs(vid_views_comp.league_detail, comp_views.league_detail)
        self.assertIs(vid_views_comp.match_detail, comp_views.match_detail)
        self.assertIs(vid_views_comp.calendar_view, comp_views.calendar_view)
        self.assertIs(vid_views_comp.friendly_match_create, comp_views.friendly_match_create)
        self.assertIs(vid_views_comp.ajax_search_teams, comp_views.ajax_search_teams)
        self.assertIs(vid_views_comp.ajax_add_match_result, comp_views.ajax_add_match_result)
        self.assertIs(vid_views_comp.ajax_acta_lineup, comp_views.ajax_acta_lineup)
        self.assertIs(vid_views_comp.standings_view, comp_views.standings_view)
        self.assertIs(vid_views_comp.ajax_matches_by_category, comp_views.ajax_matches_by_category)
        self.assertIs(vid_views_comp.ajax_teams_by_league_category, comp_views.ajax_teams_by_league_category)

    def test_forms_are_reexported(self):
        self.assertIs(vid_forms_comp.MatchAdminForm, comp_forms.MatchAdminForm)
        self.assertIs(vid_forms_comp.FriendlyMatchForm, comp_forms.FriendlyMatchForm)
        self.assertIs(vid_forms_comp.MatchResultForm, comp_forms.MatchResultForm)

    def test_calendar_feed_is_reexported(self):
        self.assertIs(vid_calendar_feed.UserMatchesFeed, comp_calendar_feed.UserMatchesFeed)


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'])
class CompetitionsViewUrlTests(TestCase):
    def setUp(self):
        from ilovevoley.users.models import Membership
        cache.clear()
        self.org = Organization.objects.create(
            slug='testclub',
            name='Test Club',
            club_team_names={'1': 'Test Club'},
            is_active=True,
        )
        User = get_user_model()
        self.user = User.objects.create_user(
            username='member', password='pass', is_staff=True, is_superuser=True
        )
        Membership.objects.create(
            user=self.user, organization=self.org, is_approved=True, role='admin'
        )
        self.category = Category.objects.create(name='Senior', is_active=True)
        self.club = Club.objects.create(
            official_name='Club Voleibol Test',
            federation_id='CLUB-TEST',
        )
        self.team = Team.objects.create(
            name='Test Club Senior',
            category=self.category,
            club=self.club,
            federation_id='TEAM-TEST-1',
            is_active=True,
        )
        self.rival_team = Team.objects.create(
            name='Rival Team Senior',
            category=self.category,
            federation_id='TEAM-TEST-2',
            is_active=True,
        )
        self.league = League.objects.create(
            name='Superliga 2',
            federation_id='LEAGUE-1',
            season=Season.objects.resolve('2026-2027'),
            is_active=True,
            visibility_type='main',
            is_our_team_related=True,
        )
        self.league.categories.add(self.category)

        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team,
            away_team=self.rival_team,
            match_date=timezone.now(),
            round_number=1,
            status='scheduled',
        )

        Standing.objects.create(
            league=self.league,
            team=self.team,
            position=1,
            played=1,
            won=1,
            total_points=3,
        )

    def test_competitions_league_list_url_resolves_and_renders(self):
        self.client.force_login(self.user)
        url = reverse('competitions:league_list')
        self.assertEqual(url, '/competitions/ligas/')
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'competitions/league_list.html')

    def test_competitions_league_detail_url_resolves_and_renders(self):
        self.client.force_login(self.user)
        url = reverse('competitions:league_detail', args=[self.league.id])
        self.assertEqual(url, f'/competitions/ligas/{self.league.id}/')
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'competitions/league_detail.html')

    def test_competitions_match_detail_url_resolves_and_renders(self):
        self.client.force_login(self.user)
        url = reverse('competitions:match_detail', args=[self.match.id])
        self.assertEqual(url, f'/competitions/partidos/{self.match.id}/')
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'competitions/match_detail.html')

    def test_competitions_calendar_view_url_resolves_and_renders(self):
        self.client.force_login(self.user)
        url = reverse('competitions:calendar_view')
        self.assertEqual(url, '/competitions/calendario/')
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'competitions/calendar.html')

    def test_calendar_invalid_month_or_year_redirects_without_500(self):
        """year/month inválidos no deben tumbar la vista con HTTP 500."""
        self.client.force_login(self.user)
        url = reverse('competitions:calendar_view')
        for params in (
            {'month': '13'},
            {'year': 'abc'},
            {'month': '0'},
            {'year': '99999', 'month': '1'},
            {'year': '9999', 'month': '12'},
            {'year': '1', 'month': '1'},
        ):
            with self.subTest(params=params):
                response = self.client.get(
                    url, params, HTTP_HOST='testclub.ilovevoley.es'
                )
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.url, url)

    def test_calendar_month_filter_uses_sargable_datetime_range(self):
        """El rango del mes debe filtrar por match_date, no por DATE(match_date)."""
        self.client.force_login(self.user)
        in_month = Match.objects.create(
            league=self.league,
            home_team=self.team,
            away_team=self.rival_team,
            match_date=timezone.make_aware(datetime(2026, 3, 15, 18, 0)),
            round_number=2,
            status='scheduled',
        )
        next_month = Match.objects.create(
            league=self.league,
            home_team=self.team,
            away_team=self.rival_team,
            match_date=timezone.make_aware(datetime(2026, 4, 1, 0, 0)),
            round_number=3,
            status='scheduled',
        )
        url = reverse('competitions:calendar_view')
        response = self.client.get(
            url,
            {'year': '2026', 'month': '3', 'all_teams': '1', 'show_all': '1'},
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        matches = list(response.context['matches'])
        self.assertIn(in_month, matches)
        self.assertNotIn(next_month, matches)
        sql = str(response.context['matches'].query).lower()
        self.assertNotIn('::date', sql)
        self.assertIn('"match_date" >=', sql)
        self.assertIn('"match_date" <', sql)

    def test_competitions_standings_view_url_resolves_and_renders(self):
        self.client.force_login(self.user)
        url = reverse('competitions:standings_view')
        self.assertEqual(url, '/competitions/clasificacion/')
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'competitions/standings.html')

    def test_standings_acepta_season_name_y_el_antiguo_season(self):
        self.client.force_login(self.user)
        url = reverse('competitions:standings_view')
        # La liga del setUp es de la temporada 2026-2027.
        for param in ('season_name=2026-27', 'season=2026-27'):
            response = self.client.get(
                f'{url}?{param}', HTTP_HOST='testclub.ilovevoley.es'
            )
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Superliga 2')

    def test_standings_ignora_season_con_id_numerico(self):
        self.client.force_login(self.user)
        url = reverse('competitions:standings_view')
        # Un id no es un nombre de temporada: no debe filtrar por un valor basura.
        response = self.client.get(
            f'{url}?season={self.league.season_id}', HTTP_HOST='testclub.ilovevoley.es'
        )
        self.assertEqual(response.status_code, 200)

    def test_competitions_friendly_match_create_url_resolves_and_renders(self):
        self.client.force_login(self.user)
        url = reverse('competitions:friendly_match_create')
        self.assertEqual(url, '/competitions/calendario/amistoso/nuevo/')
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'competitions/friendly_match_form.html')

    def test_competitions_calendar_feed_url_resolves_and_renders(self):
        token = self.user.get_or_create_calendar_token()
        url = reverse('competitions:calendar_feed', args=[token])
        self.assertEqual(url, f'/competitions/calendario/suscripcion/{token}/')
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/calendar', response['Content-Type'])

    def test_competitions_ajax_endpoints(self):
        self.client.force_login(self.user)

        # ajax_matches_by_category
        url_matches = reverse('competitions:ajax_matches_by_category')
        self.assertEqual(url_matches, '/competitions/ajax/matches-by-category/')
        r = self.client.get(url_matches, {'category_id': self.category.id}, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(r.status_code, 200)
        self.assertIn('matches', r.json())

        # ajax_teams_by_league_category
        url_teams = reverse('competitions:ajax_teams_by_league_category')
        self.assertEqual(url_teams, '/competitions/ajax/teams-by-league-category/')
        r = self.client.get(url_teams, {'league_id': self.league.id}, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(r.status_code, 200)
        self.assertIn('teams', r.json())

        # ajax_search_teams
        url_search = reverse('competitions:ajax_search_teams')
        self.assertEqual(url_search, '/competitions/ajax/search-teams/')
        r = self.client.get(url_search, {'q': 'Test'}, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(r.status_code, 200)
        self.assertIn('teams', r.json())

    def test_backwards_compatible_videos_urls_render(self):
        self.client.force_login(self.user)

        url = reverse('videos:league_list')
        self.assertEqual(url, '/videos/ligas/')
        r = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, 'competitions/league_list.html')

        url = reverse('videos:calendar_view')
        self.assertEqual(url, '/videos/calendario/')
        r = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, 'competitions/calendar.html')

    def test_anonymous_user_redirected_to_login_on_protected_views(self):
        for url_name in ['competitions:league_list', 'competitions:standings_view', 'competitions:calendar_view']:
            url = reverse(url_name)
            response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
            self.assertEqual(response.status_code, 302)
            self.assertIn('/accounts/login/', response.url)


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'rivalclub.ilovevoley.es'])
class CompetitionsTenantIsolationTests(TestCase):
    """Aísla ligas y partidos por club para impedir acceso cruzado entre tenants."""

    def setUp(self):
        from ilovevoley.users.models import Membership
        cache.clear()
        User = get_user_model()

        self.org = Organization.objects.create(
            slug='testclub', name='Test Club', is_active=True,
        )
        self.other_org = Organization.objects.create(
            slug='rivalclub', name='Rival Club', is_active=True,
        )

        self.club = Club.objects.create(official_name='Club Test', federation_id='CLUB-A')
        self.other_club = Club.objects.create(official_name='Club Rival', federation_id='CLUB-B')
        self.org.club = self.club
        self.org.save(update_fields=['club'])
        self.other_org.club = self.other_club
        self.other_org.save(update_fields=['club'])

        self.category = Category.objects.create(name='Senior', is_active=True)
        self.team = Team.objects.create(
            name='Test Senior', category=self.category, club=self.club,
            federation_id='TEAM-A1', is_active=True,
        )
        self.other_team = Team.objects.create(
            name='Rival Senior', category=self.category, club=self.other_club,
            federation_id='TEAM-B1', is_active=True,
        )
        self.foreign_team = Team.objects.create(
            name='Foreign Senior', category=self.category, club=None,
            federation_id='TEAM-C1', is_active=True,
        )

        self.manager = User.objects.create_user(username='manager', password='pass')
        Membership.objects.create(
            user=self.manager, organization=self.org, is_approved=True, role='manager',
        )
        self.member = User.objects.create_user(username='member', password='pass')
        Membership.objects.create(
            user=self.member, organization=self.org, is_approved=True, role='member',
        )

        season = Season.objects.resolve('2026-2027')
        self.league = League.objects.create(
            name='Liga Propia', federation_id='LEAGUE-A', season=season,
            is_active=True, visibility_type='main', is_our_team_related=True,
        )
        self.other_league = League.objects.create(
            name='Liga Ajena', federation_id='LEAGUE-B', season=season,
            is_active=True, visibility_type='main', is_our_team_related=True,
        )
        self.league.categories.add(self.category)
        self.other_league.categories.add(self.category)

        self.match = Match.objects.create(
            league=self.league, home_team=self.team, away_team=self.other_team,
            match_date=timezone.now(), round_number=1, status='scheduled',
        )
        self.other_match = Match.objects.create(
            league=self.other_league, home_team=self.other_team, away_team=self.foreign_team,
            match_date=timezone.now(), round_number=1, status='scheduled',
            acta_html='http://example.invalid/acta',
        )

    def test_match_detail_blocks_foreign_match(self):
        self.client.force_login(self.manager)
        own = self.client.get(
            reverse('competitions:match_detail', args=[self.match.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(own.status_code, 200)

        foreign = self.client.get(
            reverse('competitions:match_detail', args=[self.other_match.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(foreign.status_code, 404)

    def test_league_detail_blocks_foreign_league(self):
        self.client.force_login(self.manager)
        own = self.client.get(
            reverse('competitions:league_detail', args=[self.league.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(own.status_code, 200)

        foreign = self.client.get(
            reverse('competitions:league_detail', args=[self.other_league.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(foreign.status_code, 404)

    def test_add_match_result_blocks_foreign_match(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('competitions:ajax_add_match_result', args=[self.other_match.id]),
            data={'home_score': 3, 'away_score': 1},
            content_type='application/json',
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 404)
        self.other_match.refresh_from_db()
        self.assertIsNone(self.other_match.home_score)
        self.assertEqual(self.other_match.status, 'scheduled')

    def test_add_match_result_accepts_valid_score_for_own_match(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('competitions:ajax_add_match_result', args=[self.match.id]),
            data={'home_score': 3, 'away_score': 1},
            content_type='application/json',
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.match.refresh_from_db()
        self.assertEqual(self.match.home_score, 3)
        self.assertEqual(self.match.away_score, 1)
        self.assertEqual(self.match.status, 'finished')

    def test_add_match_result_rejects_invalid_score(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('competitions:ajax_add_match_result', args=[self.match.id]),
            data={'home_score': 2, 'away_score': 0},
            content_type='application/json',
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 400)
        self.match.refresh_from_db()
        self.assertIsNone(self.match.home_score)
        self.assertEqual(self.match.status, 'scheduled')

    def test_acta_lineup_blocks_foreign_match(self):
        self.client.force_login(self.manager)
        response = self.client.get(
            reverse('competitions:ajax_acta_lineup', args=[self.other_match.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 404)

    def test_team_search_requires_tenant_manager(self):
        url = reverse('competitions:ajax_search_teams')
        self.client.force_login(self.member)
        denied = self.client.get(url, {'q': 'Test'}, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(denied.status_code, 403)

        self.client.force_login(self.manager)
        allowed = self.client.get(url, {'q': 'Test'}, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(allowed.status_code, 200)
