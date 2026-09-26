from unittest.mock import patch

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

    def test_ajax_acta_lineup_rechaza_esquema_no_https(self):
        self.client.force_login(self.user)
        self.match.acta_html = 'http://127.0.0.1:8000/admin/'
        self.match.save(update_fields=['acta_html'])
        url = reverse('competitions:ajax_acta_lineup', args=[self.match.id])

        with patch('ilovevoley.core.security.requests.Session') as mock_session_cls:
            response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')

        self.assertEqual(response.status_code, 400)
        mock_session_cls.assert_not_called()

    @patch('ilovevoley.core.security.socket.getaddrinfo')
    def test_ajax_acta_lineup_rechaza_host_que_resuelve_a_ip_privada(self, mock_dns):
        import socket as _socket
        mock_dns.return_value = [
            (_socket.AF_INET, _socket.SOCK_STREAM, 6, '', ('10.0.0.5', 443)),
        ]
        self.client.force_login(self.user)
        self.match.acta_html = 'https://federatio.com/actas/1/acta.html'
        self.match.save(update_fields=['acta_html'])
        url = reverse('competitions:ajax_acta_lineup', args=[self.match.id])

        with patch('ilovevoley.core.security.requests.Session') as mock_session_cls:
            response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')

        self.assertEqual(response.status_code, 400)
        mock_session_cls.assert_not_called()

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
