from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from ilovevoley.competitions import calendar_feed as comp_calendar_feed
from ilovevoley.competitions import forms as comp_forms
from ilovevoley.competitions import views as comp_views
from ilovevoley.competitions.models import League, Match, Standing
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.teams.models import Club, Team
from ilovevoley.users.models import CategoryPreference
from ilovevoley.videos import calendar_feed as vid_calendar_feed
from ilovevoley.videos.forms import competitions as vid_forms_comp
from ilovevoley.videos.views import competitions as vid_views_comp


import re


def _count_script(content, needle):
    """Cuenta etiquetas <script src> que referencian ``needle``.

    Tolera el hash que añade ``ManifestStaticFilesStorage`` (``js/lightbox.<hash>.js``),
    que varía entre entornos con y sin ``collectstatic``.
    """
    return len(re.findall(rb'<script[^>]+src="[^"]*' + needle.encode() + rb'[^"]*"', content))


class CompetitionsReExportCompatibilityTest(SimpleTestCase):
    """Verifica que las importaciones históricas desde videos sigan funcionando."""

    def test_views_are_reexported(self):
        self.assertIs(vid_views_comp.league_list, comp_views.league_list)
        self.assertIs(vid_views_comp.league_detail, comp_views.league_detail)
        self.assertIs(vid_views_comp.match_detail, comp_views.match_detail)
        self.assertIs(vid_views_comp.match_result_card, comp_views.match_result_card)
        self.assertIs(vid_views_comp.calendar_view, comp_views.calendar_view)
        self.assertIs(vid_views_comp.friendly_match_create, comp_views.friendly_match_create)
        self.assertIs(vid_views_comp.ajax_search_teams, comp_views.ajax_search_teams)
        self.assertIs(vid_views_comp.ajax_add_match_result, comp_views.ajax_add_match_result)
        self.assertIs(vid_views_comp.ajax_edit_match_result, comp_views.ajax_edit_match_result)
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

    def _count_queries(self, url, params=None):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url, params or {}, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        return len(ctx), response

    def test_calendar_queries_do_not_grow_with_matches(self):
        from ilovevoley.content.models import Video
        self.client.force_login(self.user)
        url = reverse('competitions:calendar_view')
        Video.objects.create(title='v1', youtube_url='https://youtu.be/a', match=self.match, created_by=self.user)
        baseline, _ = self._count_queries(url)

        for i in range(3):
            m = Match.objects.create(
                league=self.league, home_team=self.team, away_team=self.rival_team,
                match_date=self.match.match_date, round_number=i + 2, status='scheduled',
            )
            for j in range(2):
                Video.objects.create(title=f'v{i}{j}', youtube_url='https://youtu.be/b', match=m, created_by=self.user)

        with_more, response = self._count_queries(url)
        self.assertEqual(with_more, baseline)
        self.assertContains(response, '2 videos')

    def test_league_detail_video_total_sums_across_matches(self):
        """El total de vídeos de la cabecera es la suma, no la concatenación (#163)."""
        from ilovevoley.content.models import Video
        self.client.force_login(self.user)
        Video.objects.create(
            title='v1', youtube_url='https://youtu.be/a', match=self.match, created_by=self.user,
        )
        other_match = Match.objects.create(
            league=self.league, home_team=self.team, away_team=self.rival_team,
            match_date=self.match.match_date, round_number=2, status='scheduled',
        )
        Video.objects.create(
            title='v2', youtube_url='https://youtu.be/b', match=other_match, created_by=self.user,
        )
        Video.objects.create(
            title='v3', youtube_url='https://youtu.be/c', match=other_match, created_by=self.user,
        )

        response = self.client.get(
            reverse('competitions:league_detail', args=[self.league.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_videos'], 3)

    def test_search_teams_queries_do_not_grow_with_results(self):
        self.client.force_login(self.user)
        url = reverse('competitions:ajax_search_teams')
        baseline, _ = self._count_queries(url, {'q': 'Senior'})

        for i in range(3):
            Team.objects.create(
                name=f'Test Club Senior {i}', category=self.category,
                club=self.club, federation_id=f'T-{i}',
            )

        with_more, response = self._count_queries(url, {'q': 'Senior'})
        self.assertEqual(with_more, baseline)
        # Solo los equipos del tenant: el rival sin club no debe colarse (#207).
        names = {team['name'] for team in response.json()['teams']}
        self.assertEqual(names, {'Test Club Senior', 'Test Club Senior 0', 'Test Club Senior 1', 'Test Club Senior 2'})

    def test_league_list_queries_do_not_grow_with_leagues_or_matches(self):
        """Verifica que el listado de ligas no sufra N+1 al crecer ligas y partidos (#Sentry 150560754)."""
        self.client.force_login(self.user)
        url = reverse('competitions:league_list')
        params = {'show_friendly': '1', 'show_past': '1'}
        baseline, response = self._count_queries(url, params)
        self.assertEqual(len(response.context['leagues']), 1)

        season = Season.objects.resolve('2026-2027')
        rival_extra = Team.objects.create(
            name='Rival Third Party', category=self.category,
            federation_id='RIVAL-TP', is_active=True,
        )
        for i in range(3):
            rival = Team.objects.create(
                name=f'Rival Extra {i}', category=self.category,
                federation_id=f'RIVAL-EXTRA-{i}', is_active=True,
            )
            lg = League.objects.create(
                name=f'Liga Extra {i}',
                federation_id=f'LEAGUE-EXTRA-{i}',
                season=season,
                is_active=True,
                visibility_type='main',
                is_our_team_related=True,
            )
            lg.categories.add(self.category)
            Standing.objects.create(
                league=lg, team=self.team, position=1, played=1, won=1, total_points=3,
            )
            # Partido retirado (no debe contar en matches_count)
            Match.objects.create(
                league=lg, home_team=self.team, away_team=rival,
                match_date=timezone.now() - timedelta(days=10),
                round_number=99, status='withdrawn',
            )
            # Partido entre rivales ajenos al club (no debe seleccionarse como próximo partido)
            Match.objects.create(
                league=lg, home_team=rival, away_team=rival_extra,
                match_date=timezone.now() + timedelta(hours=1),
                round_number=0, status='scheduled',
            )
            for m_idx in range(4):
                Match.objects.create(
                    league=lg, home_team=self.team, away_team=rival,
                    match_date=timezone.now() + timedelta(days=m_idx + 1),
                    round_number=m_idx + 1, status='scheduled',
                    is_friendly=(m_idx % 2 == 1),
                )

        with CaptureQueriesContext(connection) as ctx2:
            response2 = self.client.get(url, params, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(len(response2.context['leagues']), 4)
        self.assertEqual(len(ctx2), baseline)

        # Verificar que el partido retirado no se cuenta en matches_count (4 + 1 ajeno = 5)
        extra_league = next(l for l in response2.context['leagues'] if l.name == 'Liga Extra 0')
        self.assertEqual(extra_league.matches_count, 5)
        # Verificar que el próximo partido oficial mostrado es del club y no el del rival ajeno
        self.assertIsNotNone(extra_league.next_official_match)
        self.assertIn('Test Club Senior', extra_league.next_official_match.home_team_display)

    def test_acta_lineup_is_fetched_once_and_cached(self):
        self.client.force_login(self.user)
        self.match.acta_html = 'https://federacion.example/acta/1'
        self.match.save(update_fields=['acta_html'])
        parsed = {
            'sets': [], 'home_team': 'A', 'away_team': 'B', 'home_captain': None, 'away_captain': None,
            'home_convocados': [], 'away_convocados': [],
        }
        url = reverse('competitions:ajax_acta_lineup', args=[self.match.id])
        with patch.object(comp_views, 'safe_get', return_value=b'<html></html>') as get, \
                patch.object(comp_views, 'parse_acta_lineup', return_value=parsed):
            for _ in range(2):
                r = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
                self.assertEqual(r.status_code, 200)
        get.assert_called_once()

    def test_acta_persistida_no_se_descarga_aunque_expire_la_cache(self):
        """Aunque venza la caché, el acta ya persistida no se vuelve a descargar."""
        self.client.force_login(self.user)
        self.match.acta_html = 'https://federacion.example/acta/2'
        self.match.save(update_fields=['acta_html'])
        parsed = {
            'sets': [], 'home_team': 'A', 'away_team': 'B', 'home_captain': None, 'away_captain': None,
            'home_convocados': [], 'away_convocados': [],
        }
        url = reverse('competitions:ajax_acta_lineup', args=[self.match.id])
        with patch.object(comp_views, 'safe_get', return_value=b'<html></html>') as get, \
                patch.object(comp_views, 'parse_acta_lineup', return_value=parsed) as parse:
            self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
            cache.clear()
            r = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')

        self.assertEqual(r.status_code, 200)
        get.assert_called_once()
        parse.assert_called_once()
        self.match.refresh_from_db()
        self.assertIsNotNone(self.match.acta_data)

    def test_standings_acepta_season_name_y_el_antiguo_season(self):
        self.client.force_login(self.user)
        other_league = League.objects.create(
            name='Liga Temporada Anterior',
            federation_id='LEAGUE-OLD',
            season=Season.objects.resolve('2025-2026'),
            is_active=True,
            visibility_type='main',
            is_our_team_related=True,
        )
        other_league.categories.add(self.category)
        Standing.objects.create(
            league=other_league, team=self.team, position=1, played=1, won=1, total_points=3,
        )

        url = reverse('competitions:standings_view')
        # La liga del setUp es de la temporada 2026-2027.
        for param in ('season_name=2026-27', 'season=2026-27'):
            with self.subTest(param=param):
                response = self.client.get(
                    f'{url}?{param}', HTTP_HOST='testclub.ilovevoley.es'
                )
                self.assertEqual(response.status_code, 200)
                standings_by_league = response.context['standings_by_league']
                self.assertIn('Superliga 2', standings_by_league)
                self.assertNotIn('Liga Temporada Anterior', standings_by_league)

    def test_standings_ignora_season_con_id_numerico(self):
        self.client.force_login(self.user)
        other_league = League.objects.create(
            name='Liga Temporada Anterior',
            federation_id='LEAGUE-OLD',
            season=Season.objects.resolve('2025-2026'),
            is_active=True,
            visibility_type='main',
            is_our_team_related=True,
        )
        other_league.categories.add(self.category)
        Standing.objects.create(
            league=other_league, team=self.team, position=1, played=1, won=1, total_points=3,
        )

        url = reverse('competitions:standings_view')
        # Un id no es un nombre de temporada: se ignora y no filtra por un valor basura.
        response = self.client.get(
            f'{url}?season={self.league.season_id}', HTTP_HOST='testclub.ilovevoley.es'
        )
        self.assertEqual(response.status_code, 200)
        standings_by_league = response.context['standings_by_league']
        self.assertIn('Superliga 2', standings_by_league)
        # Ignorado el id, rige el valor por defecto: solo la temporada activa.
        self.assertNotIn('Liga Temporada Anterior', standings_by_league)

    def test_competitions_calendar_feed_requires_valid_token_and_lists_matches(self):
        CategoryPreference.objects.create(
            user=self.user, organization=self.org
        ).categories.add(self.category)
        token = self.user.get_or_create_calendar_token()
        url = reverse('competitions:calendar_feed', args=[token])

        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/calendar', response['Content-Type'])
        self.assertIn(f'partido-{self.match.id}@', response.content.decode())

        denied = self.client.get(
            reverse('competitions:calendar_feed', args=['token-invalido']),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(denied.status_code, 404)

    def test_calendar_feed_item_guid_defaults_to_videosvoley_for_compatibility(self):
        feed = comp_calendar_feed.UserMatchesFeed()
        guid = feed.item_guid(self.match)
        self.assertEqual(guid, f'partido-{self.match.id}@videosvoley.com')

    @override_settings(CALENDAR_FEED_DOMAIN='ilovevoley.es')
    def test_calendar_feed_item_guid_supports_configured_domain(self):
        feed = comp_calendar_feed.UserMatchesFeed()
        guid = feed.item_guid(self.match)
        self.assertEqual(guid, f'partido-{self.match.id}@ilovevoley.es')

    def test_calendar_feed_location_uses_venue_full_address(self):
        from ilovevoley.competitions.models import Venue
        from ilovevoley.users.models import CategoryPreference
        pref = CategoryPreference.objects.create(user=self.user, organization=self.org)
        pref.categories.add(self.category)

        venue = Venue.objects.create(
            name="Pavelló Test Calendar Feed",
            address="Son Serra s/n",
            city="Bunyola",
            google_maps_url="https://maps.app.goo.gl/bunyola"
        )
        self.match.venue_ref = venue
        self.match.save(update_fields=['venue_ref'])

        token = self.user.get_or_create_calendar_token()
        url = reverse('competitions:calendar_feed', args=[token])
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        content = response.content.decode('utf-8')
        unfolded = content.replace('\r\n ', '')

        self.assertIn("LOCATION:Pavelló Test Calendar Feed\\, Son Serra s/n\\, Bunyola", unfolded)
        self.assertIn("https://maps.app.goo.gl/bunyola", unfolded)
        self.assertIn("📍 Ubicación:", unfolded)
        self.assertIn("🗺️ Cómo llegar:", unfolded)

    def test_calendar_feed_location_infers_from_home_club_default_venue(self):
        from ilovevoley.competitions.models import Venue
        from ilovevoley.users.models import CategoryPreference
        pref = CategoryPreference.objects.create(user=self.user, organization=self.org)
        pref.categories.add(self.category)

        venue = Venue.objects.create(
            name="Pavelló Test Blanquerna Inferred",
            address="Carrer des Caülls, 1",
            city="Marratxí"
        )
        self.match.venue = ""
        self.match.venue_ref = None
        self.match.home_team.club.default_venue = venue
        self.match.home_team.club.save(update_fields=['default_venue'])
        self.match.save()

        token = self.user.get_or_create_calendar_token()
        url = reverse('competitions:calendar_feed', args=[token])
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        content = response.content.decode('utf-8')

        self.assertIn("Pavelló Test Blanquerna Inferred", content)

    def test_competitions_ajax_endpoints(self):
        self.client.force_login(self.user)
        other_category = Category.objects.create(name='Juvenil', is_active=True)
        Team.objects.create(
            name='Test Club Juvenil', category=other_category, club=self.club,
            federation_id='TEAM-TEST-3', is_active=True,
        )

        # ajax_matches_by_category: solo partidos del club del tenant en esa categoría.
        url_matches = reverse('competitions:ajax_matches_by_category')
        r = self.client.get(url_matches, {'category_id': self.category.id}, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(r.status_code, 200)
        match_ids = {m['id'] for m in r.json()['matches']}
        self.assertIn(self.match.id, match_ids)

        r = self.client.get(url_matches, {'category_id': other_category.id}, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(self.match.id, {m['id'] for m in r.json()['matches']})

        # ajax_teams_by_league_category: solo equipos de las categorías de la liga.
        url_teams = reverse('competitions:ajax_teams_by_league_category')
        r = self.client.get(url_teams, {'league_id': self.league.id}, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(r.status_code, 200)
        team_names = {t['text'] for t in r.json()['teams']}
        self.assertIn('Test Club Senior (Senior)', team_names)
        self.assertIn('Rival Team Senior (Senior)', team_names)
        self.assertNotIn('Test Club Juvenil (Juvenil)', team_names)

        # ajax_search_teams: solo equipos del club del tenant.
        url_search = reverse('competitions:ajax_search_teams')
        r = self.client.get(url_search, {'q': 'Test'}, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(r.status_code, 200)
        search_names = {t['name'] for t in r.json()['teams']}
        self.assertIn(self.team.name, search_names)
        self.assertNotIn(self.rival_team.name, search_names)

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

    def test_legacy_videos_urls_redirect_permanently_to_canonical(self):
        """Los marcadores antiguos /videos/... responden 301 hacia su app de dominio."""
        self.client.force_login(self.user)

        redirects = [
            ('/videos/ligas/', '/competitions/ligas/'),
            ('/videos/calendario/', '/competitions/calendario/'),
            ('/videos/partidos/1/', '/competitions/partidos/1/'),
        ]

        for legacy_url, canonical_url in redirects:
            r = self.client.get(legacy_url, HTTP_HOST='testclub.ilovevoley.es')
            self.assertEqual(r.status_code, 301, legacy_url)
            self.assertEqual(r.headers['Location'], canonical_url, legacy_url)

    def test_calendar_embeds_matches_via_json_script_not_innerhtml_literals(self):
        """DOM-XSS (#89): datos de partido van en json_script; el modal escapa HTML."""
        import json
        import re

        xss_name = '<img src=x onerror=alert(1)>'
        self.rival_team.name = xss_name
        self.rival_team.save()

        self.client.force_login(self.user)
        response = self.client.get(
            reverse('competitions:calendar_view'),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        self.assertIn('id="calendar-data"', content)
        self.assertNotIn("home_team: '{{", content)
        self.assertIn('${esc(match.home_team)}', content)
        self.assertIn('${esc(match.away_team)}', content)
        # json_script escapa < como \\u003C: el payload crudo no debe aparecer en el HTML
        self.assertNotIn(xss_name, content)
        self.assertIn('\\u003Cimg', content)

        match_script = re.search(
            r'<script[^>]*id="calendar-data"[^>]*>(.*?)</script>',
            content,
            re.DOTALL,
        )
        self.assertIsNotNone(match_script)
        payload = json.loads(match_script.group(1))
        calendar_match = next(m for m in payload['matches'] if m['id'] == self.match.id)
        self.assertEqual(calendar_match['away_team'], xss_name)
        self.assertEqual(calendar_match['round_number'], 1)
        self.assertIsInstance(calendar_match['round_number'], int)

    def test_friendly_match_form_builds_autocomplete_without_team_innerhtml(self):
        """DOM-XSS (#89): el autocompletado no interpola nombres en innerHTML."""
        self.client.force_login(self.user)
        response = self.client.get(
            reverse('competitions:friendly_match_create'),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn('${team.name}', content)
        self.assertNotIn('${team.display}', content)
        self.assertNotIn('${teamName}', content)
        self.assertIn('textContent', content)


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'])
class MatchResultCardViewTests(TestCase):
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
            username='card-admin', password='pass', is_staff=True, is_superuser=True
        )
        Membership.objects.create(
            user=self.user, organization=self.org, is_approved=True, role='admin'
        )
        self.category = Category.objects.create(name='Senior', is_active=True)
        self.club = Club.objects.create(
            official_name='Club Voleibol Test',
            federation_id='CLUB-CARD',
        )
        self.team = Team.objects.create(
            name='Test Club Senior',
            category=self.category,
            club=self.club,
            federation_id='TEAM-CARD-1',
            is_active=True,
        )
        self.rival_team = Team.objects.create(
            name='Rival Team Senior',
            category=self.category,
            federation_id='TEAM-CARD-2',
            is_active=True,
        )
        self.league = League.objects.create(
            name='Superliga 2',
            federation_id='LEAGUE-CARD',
            season=Season.objects.resolve('2026-2027'),
            is_active=True,
            visibility_type='main',
            is_our_team_related=True,
        )
        self.league.categories.add(self.category)
        self.finished = Match.objects.create(
            league=self.league,
            home_team=self.team,
            away_team=self.rival_team,
            match_date=timezone.now() - timezone.timedelta(days=1),
            home_score=3,
            away_score=1,
            status='finished',
            federation_id='CARD-FIN-1',
        )
        self.scheduled = Match.objects.create(
            league=self.league,
            home_team=self.team,
            away_team=self.rival_team,
            match_date=timezone.now() + timezone.timedelta(days=1),
            status='scheduled',
            federation_id='CARD-SCH-1',
        )
        self.client.force_login(self.user)

    def _url(self, match_id, fmt=None):
        url = reverse('competitions:match_result_card', args=[match_id])
        if fmt:
            url += f'?format={fmt}'
        return url

    def test_finished_match_returns_png(self):
        with patch(
            'ilovevoley.competitions.result_card.fetch_logo_bytes',
            return_value=None,
        ):
            response = self.client.get(
                self._url(self.finished.id),
                HTTP_HOST='testclub.ilovevoley.es',
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertTrue(response.content.startswith(b'\x89PNG'))

    def test_story_format_has_expected_dimensions(self):
        from io import BytesIO

        from PIL import Image

        with patch(
            'ilovevoley.competitions.result_card.fetch_logo_bytes',
            return_value=None,
        ):
            response = self.client.get(
                self._url(self.finished.id, 'story'),
                HTTP_HOST='testclub.ilovevoley.es',
            )

        self.assertEqual(response.status_code, 200)
        image = Image.open(BytesIO(response.content))
        self.assertEqual(image.size, (1080, 1920))

    def test_not_finished_returns_json_400(self):
        response = self.client.get(
            self._url(self.scheduled.id),
            HTTP_HOST='testclub.ilovevoley.es',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertIn('finalizado', response.json()['error'].lower())

    def test_invalid_format_returns_json_400(self):
        response = self.client.get(
            self._url(self.finished.id, 'banner'),
            HTTP_HOST='testclub.ilovevoley.es',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('formato', response.json()['error'].lower())

    def test_invalid_style_returns_json_400(self):
        response = self.client.get(
            self._url(self.finished.id, 'square') + '&style=banner',
            HTTP_HOST='testclub.ilovevoley.es',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('estilo', response.json()['error'].lower())

    def test_marco_style_without_photo_id_returns_json_400(self):
        response = self.client.get(
            self._url(self.finished.id, 'square') + '&style=marco',
            HTTP_HOST='testclub.ilovevoley.es',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('foto', response.json()['error'].lower())

    def test_marco_style_with_non_numeric_photo_id_returns_json_400(self):
        """photo_id no numerico no debe reventar el lookup con un 500."""
        for bad_photo_id in ('abc', '²'):
            with self.subTest(photo_id=bad_photo_id):
                response = self.client.get(
                    self._url(self.finished.id, 'square')
                    + f'&style=marco&photo_id={bad_photo_id}',
                    HTTP_HOST='testclub.ilovevoley.es',
                )

                self.assertEqual(response.status_code, 400)
                self.assertIn('foto', response.json()['error'].lower())

    def test_marco_style_with_approved_photo_returns_png(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from ilovevoley.content.models import Image

        tiny_gif = (
            b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
            b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00'
            b'\x00\x02\x02D\x01\x00;'
        )
        photo = Image.objects.create(
            image=SimpleUploadedFile('x.jpg', tiny_gif, content_type='image/jpeg'),
            title='Foto del partido',
            match=self.finished,
            organization=self.org,
            status='approved',
            uploaded_by=self.user,
        )

        with patch(
            'ilovevoley.competitions.result_card.fetch_logo_bytes',
            return_value=None,
        ):
            response = self.client.get(
                self._url(self.finished.id, 'square') + f'&style=marco&photo_id={photo.id}',
                HTTP_HOST='testclub.ilovevoley.es',
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')

    def test_marco_style_with_missing_photo_file_returns_json_400(self):
        """El fichero de la foto puede faltar en el storage aunque el registro exista (#241)."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        from ilovevoley.content.models import Image

        tiny_gif = (
            b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
            b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00'
            b'\x00\x02\x02D\x01\x00;'
        )
        photo = Image.objects.create(
            image=SimpleUploadedFile('x.jpg', tiny_gif, content_type='image/jpeg'),
            title='Foto sin fichero en disco',
            match=self.finished,
            organization=self.org,
            status='approved',
            uploaded_by=self.user,
        )
        photo.image.storage.delete(photo.image.name)

        response = self.client.get(
            self._url(self.finished.id, 'square') + f'&style=marco&photo_id={photo.id}',
            HTTP_HOST='testclub.ilovevoley.es',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('foto', response.json()['error'].lower())

    def test_marco_style_with_photo_from_other_org_returns_json_400(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from ilovevoley.content.models import Image

        tiny_gif = (
            b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
            b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00'
            b'\x00\x02\x02D\x01\x00;'
        )
        other_org = Organization.objects.create(
            slug='otherclub', name='Other Club', is_active=True
        )
        photo = Image.objects.create(
            image=SimpleUploadedFile('x.jpg', tiny_gif, content_type='image/jpeg'),
            title='Foto de otro club',
            match=self.finished,
            organization=other_org,
            status='approved',
            uploaded_by=self.user,
        )

        response = self.client.get(
            self._url(self.finished.id, 'square') + f'&style=marco&photo_id={photo.id}',
            HTTP_HOST='testclub.ilovevoley.es',
        )

        self.assertEqual(response.status_code, 400)

    def _approved_photo(self, organization=None):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from ilovevoley.content.models import Image

        tiny_gif = (
            b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
            b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00'
            b'\x00\x02\x02D\x01\x00;'
        )
        return Image.objects.create(
            image=SimpleUploadedFile('x.jpg', tiny_gif, content_type='image/jpeg'),
            title='Foto', match=self.finished, organization=organization or self.org,
            status='approved', uploaded_by=self.user,
        )

    def _save_composition(self, **payload):
        import json

        return self.client.post(
            reverse('competitions:story_composition_save', args=[self.finished.id]),
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_HOST='testclub.ilovevoley.es',
        )

    def test_custom_style_preview_is_downscaled_png(self):
        from io import BytesIO

        from PIL import Image as PILImage

        photo = self._approved_photo()
        with patch('ilovevoley.competitions.result_card.fetch_logo_bytes', return_value=None):
            response = self.client.get(
                self._url(self.finished.id, 'story')
                + f'&style=personalizada&photo_id={photo.id}&preview=1'
                + '&layout={"score":{"y":0.3},"photo":{"zoom":1.5}}',
                HTTP_HOST='testclub.ilovevoley.es',
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Content-Disposition', response)
        self.assertEqual(PILImage.open(BytesIO(response.content)).size, (540, 960))

    def test_saved_composition_is_normalized_and_renders_for_its_owner_only(self):
        photo = self._approved_photo()
        saved = self._save_composition(
            photo_id=photo.id, format='story', layout={'score': {'scale': 99}}
        )
        self.assertEqual(saved.status_code, 200)
        composition_id = saved.json()['id']
        self.assertEqual(saved.json()['layout']['score']['scale'], 1.2)

        url = reverse('competitions:match_result_card', args=[self.finished.id])
        with patch('ilovevoley.competitions.result_card.fetch_logo_bytes', return_value=None):
            own = self.client.get(
                f'{url}?composition={composition_id}', HTTP_HOST='testclub.ilovevoley.es'
            )
        self.assertEqual(own.status_code, 200)
        self.assertTrue(own.content.startswith(b'\x89PNG'))
        with patch('ilovevoley.competitions.result_card.fetch_logo_bytes', return_value=None):
            thumb = self.client.get(
                f'{url}?composition={composition_id}&preview=1', HTTP_HOST='testclub.ilovevoley.es'
            )
        # Las miniaturas de composiciones guardadas son cacheables (perfil); la preview del editor no.
        self.assertIn('max-age=2592000', thumb['Cache-Control'])

        other = get_user_model().objects.create_user(username='other', password='pass')
        from ilovevoley.users.models import Membership

        Membership.objects.create(user=other, organization=self.org, is_approved=True, role='member')
        self.client.force_login(other)
        stolen = self.client.get(
            f'{url}?composition={composition_id}', HTTP_HOST='testclub.ilovevoley.es'
        )
        self.assertEqual(stolen.status_code, 404)
        overwrite = self._save_composition(photo_id=photo.id, id=composition_id)
        self.assertEqual(overwrite.status_code, 404)

    def test_only_owner_can_delete_composition(self):
        from ilovevoley.competitions.models import StoryComposition
        from ilovevoley.users.models import Membership

        photo = self._approved_photo()
        composition_id = self._save_composition(photo_id=photo.id).json()['id']
        url = reverse('competitions:story_composition_delete', args=[composition_id])

        other = get_user_model().objects.create_user(username='other-del', password='pass')
        Membership.objects.create(user=other, organization=self.org, is_approved=True, role='member')
        self.client.force_login(other)
        denied = self.client.post(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(denied.status_code, 404)
        self.assertTrue(StoryComposition.objects.filter(id=composition_id).exists())

        self.client.force_login(self.user)
        deleted = self.client.post(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(deleted.status_code, 302)
        self.assertFalse(StoryComposition.objects.filter(id=composition_id).exists())

    def test_save_rejects_photo_from_other_organization(self):
        other_org = Organization.objects.create(slug='otherclub', name='Other Club', is_active=True)
        photo = self._approved_photo(organization=other_org)

        response = self._save_composition(photo_id=photo.id, format='story')

        self.assertEqual(response.status_code, 400)

    def test_missing_match_returns_json_404(self):
        response = self.client.get(
            self._url(999999),
            HTTP_HOST='testclub.ilovevoley.es',
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {'error': 'Partido no encontrado'})

    def test_acta_sets_are_extracted_and_cached_for_rendering(self):
        self.finished.acta_html = 'https://federacion.example/acta/card'
        self.finished.save(update_fields=['acta_html'])
        lineup = {
            'sets': [
                {
                    'teams': [
                        {'name': 'Test Club Senior', 'points': 25},
                        {'name': 'Rival Team Senior', 'points': 19},
                    ]
                },
                {
                    'teams': [
                        {'name': 'Rival Team Senior', 'points': 25},
                        {'name': 'Test Club Senior', 'points': 21},
                    ]
                },
            ]
        }
        png = b'\x89PNG\r\n\x1a\n'

        with (
            patch.object(comp_views, 'safe_get', return_value=b'<html></html>') as get,
            patch.object(comp_views, 'parse_acta_lineup', return_value=lineup) as parse,
            patch.object(comp_views, 'render_result_card', return_value=png) as render_card,
        ):
            for _ in range(2):
                response = self.client.get(
                    self._url(self.finished.id),
                    HTTP_HOST='testclub.ilovevoley.es',
                )
                self.assertEqual(response.status_code, 200)

        get.assert_called_once()
        parse.assert_called_once()
        self.assertEqual(render_card.call_count, 2)
        self.assertEqual(render_card.call_args.kwargs['sets'], [(25, 19), (21, 25)])

    def test_acta_data_avoids_http_fetch_for_card(self):
        """Con el JSON del acta en BD no se descarga el HTML para la tarjeta (#200)."""
        self.finished.acta_data = {
            'sets': [
                {
                    'teams': [
                        {'name': 'Test Club Senior', 'points': 25},
                        {'name': 'Rival Team Senior', 'points': 19},
                    ]
                },
            ]
        }
        self.finished.save(update_fields=['acta_data'])
        png = b'\x89PNG\r\n\x1a\n'

        with (
            patch.object(comp_views, 'safe_get') as get,
            patch.object(comp_views, 'render_result_card', return_value=png) as render_card,
        ):
            response = self.client.get(
                self._url(self.finished.id),
                HTTP_HOST='testclub.ilovevoley.es',
            )

        self.assertEqual(response.status_code, 200)
        get.assert_not_called()
        self.assertEqual(render_card.call_args.kwargs['sets'], [(25, 19)])

    def test_unreachable_acta_still_returns_card_without_sets(self):
        self.finished.acta_html = 'https://federacion.example/acta/card'
        self.finished.save(update_fields=['acta_html'])
        png = b'\x89PNG\r\n\x1a\n'

        with (
            patch.object(comp_views, 'safe_get', side_effect=OSError('red caída')),
            patch.object(comp_views, 'render_result_card', return_value=png) as render_card,
        ):
            response = self.client.get(
                self._url(self.finished.id),
                HTTP_HOST='testclub.ilovevoley.es',
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertEqual(render_card.call_args.kwargs['sets'], [])


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

    def test_match_detail_allows_foreign_match_without_media(self):
        self.client.force_login(self.manager)
        own = self.client.get(
            reverse('competitions:match_detail', args=[self.match.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(own.status_code, 200)
        self.assertTrue(own.context['is_own_match'])

        foreign = self.client.get(
            reverse('competitions:match_detail', args=[self.other_match.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(foreign.status_code, 200)
        self.assertFalse(foreign.context['is_own_match'])
        self.assertEqual(list(foreign.context['videos']), [])
        self.assertEqual(list(foreign.context['images']), [])
        self.assertFalse(foreign.context['can_manage_videos'])
        self.assertFalse(foreign.context['can_edit_result'])

    def test_match_detail_loads_lightbox_script_once(self):
        """base.html ya carga lightbox.js; la ficha no debe duplicarlo (#209)."""
        self.client.force_login(self.manager)
        response = self.client.get(
            reverse('competitions:match_detail', args=[self.match.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(_count_script(response.content, 'js/lightbox'), 1)

    def test_match_images_loads_lightbox_script_once(self):
        """base.html ya carga lightbox.js; las imágenes de partido no lo duplican (#209)."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        from ilovevoley.content.models import Image

        gif = (
            b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
            b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
        )
        Image.objects.create(
            image=SimpleUploadedFile('photo.gif', gif, content_type='image/gif'),
            title='Foto', uploaded_by=self.manager, match=self.match,
            organization=self.org, status='approved',
        )
        self.client.force_login(self.manager)
        response = self.client.get(
            reverse('content:match_images', args=[self.match.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(_count_script(response.content, 'js/lightbox'), 1)

    def test_match_detail_hides_foreign_org_media(self):
        """Vídeos e imágenes de otra organización no se listan en la ficha del partido (#200)."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        from ilovevoley.content.models import Image, Video

        gif = (
            b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
            b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
        )
        Video.objects.create(
            title='Propio', youtube_url='https://youtu.be/abc', created_by=self.manager,
            match=self.match, organization=self.org,
        )
        Video.objects.create(
            title='Ajeno', youtube_url='https://youtu.be/def', created_by=self.manager,
            match=self.match, organization=self.other_org,
        )
        Image.objects.create(
            image=SimpleUploadedFile('own.gif', gif, content_type='image/gif'),
            title='Propia', uploaded_by=self.manager, match=self.match,
            organization=self.org, status='approved',
        )
        Image.objects.create(
            image=SimpleUploadedFile('foreign.gif', gif, content_type='image/gif'),
            title='Ajena', uploaded_by=self.manager, match=self.match,
            organization=self.other_org, status='approved',
        )

        self.client.force_login(self.manager)
        response = self.client.get(
            reverse('competitions:match_detail', args=[self.match.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([v.title for v in response.context['videos']], ['Propio'])
        self.assertEqual([i.title for i in response.context['images']], ['Propia'])

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

    @patch('ilovevoley.competitions.views.MatchResultForm.save')
    def test_add_match_result_internal_error_does_not_leak_exception(self, mock_save):
        mock_save.side_effect = RuntimeError("Database connection string password leaked")
        self.client.force_login(self.manager)
        with self.assertLogs('ilovevoley.competitions.views', level='ERROR') as captured_logs:
            response = self.client.post(
                reverse('competitions:ajax_add_match_result', args=[self.match.id]),
                data={'home_score': 3, 'away_score': 1},
                content_type='application/json',
                HTTP_HOST='testclub.ilovevoley.es',
            )
        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], 'Error interno al guardar el resultado.')
        self.assertNotIn("Database connection string", data['error'])
        self.assertTrue(any("Error al guardar resultado del partido" in msg for msg in captured_logs.output))

    def test_add_match_result_with_set_scores_derives_score(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('competitions:ajax_add_match_result', args=[self.match.id]),
            data={'set_scores': [[25, 20], [25, 18], [25, 22]]},
            content_type='application/json',
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.match.refresh_from_db()
        self.assertEqual((self.match.home_score, self.match.away_score), (3, 0))
        self.assertEqual(self.match.set_scores, [[25, 20], [25, 18], [25, 22]])

    def test_edit_match_result_updates_set_scores(self):
        self.match.status = 'finished'
        self.match.home_score = 3
        self.match.away_score = 0
        self.match.save()

        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('competitions:ajax_edit_match_result', args=[self.match.id]),
            data={'set_scores': [[25, 20], [20, 25], [25, 23], [25, 18]]},
            content_type='application/json',
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()['success'])
        self.match.refresh_from_db()
        self.assertEqual((self.match.home_score, self.match.away_score), (3, 1))
        self.assertEqual(
            self.match.set_scores, [[25, 20], [20, 25], [25, 23], [25, 18]]
        )

    def test_edit_match_result_blocks_foreign_match(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('competitions:ajax_edit_match_result', args=[self.other_match.id]),
            data={'set_scores': [[25, 20], [25, 18], [25, 22]]},
            content_type='application/json',
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 404)

    def test_edit_match_result_rejects_unfinished_match(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('competitions:ajax_edit_match_result', args=[self.match.id]),
            data={'set_scores': [[25, 20], [25, 18], [25, 22]]},
            content_type='application/json',
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 400)

    def test_edit_match_result_rejects_match_with_acta(self):
        with_acta = Match.objects.create(
            league=self.league, home_team=self.team, away_team=self.other_team,
            match_date=timezone.now(), round_number=2, status='finished',
            home_score=3, away_score=0, acta_html='http://example.invalid/acta',
        )
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('competitions:ajax_edit_match_result', args=[with_acta.id]),
            data={'set_scores': [[25, 20], [25, 18], [25, 22]]},
            content_type='application/json',
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 400)

    def test_acta_lineup_allows_foreign_match_and_isolates_persons(self):
        """Permite cargar el acta de un partido ajeno, la persiste y no resuelve personas de otros clubes."""
        self.client.force_login(self.manager)
        sample_lineup = {
            'home_team': 'Rival Senior',
            'away_team': 'Other Senior',
            'home_captain': '1',
            'away_captain': '2',
            'home_convocados': ['1 Foreign Player'],
            'away_convocados': ['2 Other Player'],
            'sets': [{'title': 'SET 1', 'time': '20m', 'teams': [{'name': 'Rival Senior', 'points': 25, 'lineup': []}]}],
        }
        with patch('ilovevoley.competitions.views.safe_get', return_value=b'<html></html>'), \
             patch('ilovevoley.competitions.views.parse_acta_lineup', return_value=sample_lineup):
            response = self.client.get(
                reverse('competitions:ajax_acta_lineup', args=[self.other_match.id]),
                HTTP_HOST='testclub.ilovevoley.es',
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['home_convocados'][0]['name_acta'], 'Foreign Player')
        self.assertIsNone(data['home_convocados'][0]['person'])
        self.other_match.refresh_from_db()
        self.assertIsNotNone(self.other_match.acta_data)

    def test_team_search_requires_tenant_manager(self):
        url = reverse('competitions:ajax_search_teams')
        self.client.force_login(self.member)
        denied = self.client.get(url, {'q': 'Test'}, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(denied.status_code, 403)

        self.client.force_login(self.manager)
        allowed = self.client.get(url, {'q': 'Test'}, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(allowed.status_code, 200)

    def _standing(self, league, team):
        return Standing.objects.create(
            league=league, team=team, position=1, played=1, won=1, total_points=3,
        )

    def test_standings_view_groups_leagues_by_category_tab(self):
        """Cada categoría es una pestaña con todos sus grupos, también los de otros clubes."""
        cadete = Category.objects.create(name='Cadete', is_active=True)
        self.other_league.categories.set([cadete])
        self._standing(self.league, self.team)
        self._standing(self.other_league, self.other_team)
        self.client.force_login(self.member)
        response = self.client.get(
            reverse('competitions:standings_view'), HTTP_HOST='testclub.ilovevoley.es',
        )
        tabs = {t['slug']: [name for name, _ in t['leagues']] for t in response.context['category_tabs']}
        self.assertEqual(tabs, {'senior': ['Liga Propia'], 'cadete': ['Liga Ajena']})

    def test_standings_view_uncategorized_tab_slug_is_language_independent(self):
        """Las ligas sin categoría van a la pestaña 'otras' en cualquier idioma, para que los enlaces no se rompan."""
        self.league.categories.clear()
        self._standing(self.league, self.team)
        self.client.force_login(self.member)
        response = self.client.get(
            reverse('competitions:standings_view'),
            HTTP_HOST='testclub.ilovevoley.es', HTTP_ACCEPT_LANGUAGE='ca',
        )
        self.assertEqual(response.context['request'].LANGUAGE_CODE, 'ca')
        self.assertEqual([t['slug'] for t in response.context['category_tabs']], ['otras'])

    def test_standings_view_default_tab_prefers_user_preference_then_club_category(self):
        cadete = Category.objects.create(name='Cadete', is_active=True)
        self.other_league.categories.set([cadete])
        self._standing(self.league, self.team)
        self._standing(self.other_league, self.other_team)
        self.client.force_login(self.member)
        url = reverse('competitions:standings_view')

        # Sin preferencias: la categoría donde compite el club (Senior, aunque Cadete va antes)
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.context['active_slug'], 'senior')

        # Las preferencias del usuario en este club mandan sobre la categoría del club
        CategoryPreference.objects.create(
            user=self.member, organization=self.org
        ).categories.add(cadete)
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.context['active_slug'], 'cadete')

        # ?category= explícito manda sobre todo; un slug inexistente se ignora
        response = self.client.get(f'{url}?category=senior', HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.context['active_slug'], 'senior')
        response = self.client.get(f'{url}?category=nope', HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.context['active_slug'], 'cadete')

    def test_standings_view_defaults_to_current_season_leagues(self):
        """Sin filtro de temporada ni show_archived, solo se muestran ligas de la temporada activa."""
        past_season = Season.objects.create(name='2025-26', start_year=2025, end_year=2026, is_current=False)
        past_league = League.objects.create(
            name='Liga Ajena Pasada', federation_id='liga-ajena-pasada', season=past_season,
            is_active=True, visibility_type='main', is_our_team_related=False,
        )
        self._standing(self.other_league, self.other_team)
        self._standing(past_league, self.other_team)
        self.client.force_login(self.member)
        url = reverse('competitions:standings_view')
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertIn('Liga Ajena', response.context['standings_by_league'])
        self.assertNotIn('Liga Ajena Pasada', response.context['standings_by_league'])

        # Al filtrar explícitamente por la temporada pasada, sí se incluye
        response_past = self.client.get(f'{url}?season_name=2025-26', HTTP_HOST='testclub.ilovevoley.es')
        self.assertIn('Liga Ajena Pasada', response_past.context['standings_by_league'])
        self.assertNotIn('Liga Ajena', response_past.context['standings_by_league'])


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'otherclub.ilovevoley.es', 'noclub.ilovevoley.es', 'localhost'])
class MatchChangesReviewViewTest(TestCase):
    def setUp(self):
        cache.clear()
        self.org = Organization.objects.create(
            slug='testclub', name='Test Club', is_active=True,
        )
        self.other_org = Organization.objects.create(
            slug='otherclub', name='Other Club', is_active=True,
        )
        User = get_user_model()
        from ilovevoley.users.models import Membership
        self.manager_user = User.objects.create_user(username='manager_user', email='manager@testclub.es')
        Membership.objects.create(
            user=self.manager_user, organization=self.org, role='manager', is_approved=True
        )
        self.regular_member = User.objects.create_user(username='regular_member', email='member@testclub.es')
        Membership.objects.create(
            user=self.regular_member, organization=self.org, role='member', is_approved=True
        )

        self.club = Club.objects.create(official_name='Test Club', federation_id='CLUB-TEST')
        self.other_club = Club.objects.create(official_name='Other Club', federation_id='CLUB-OTHER')
        self.org.club = self.club
        self.org.save()
        self.other_org.club = self.other_club
        self.other_org.save()

        self.category = Category.objects.create(name='Senior', is_active=True)
        self.team = Team.objects.create(
            name='Test Club Senior', category=self.category, club=self.club, federation_id='TEAM-1', is_active=True
        )
        self.rival_team = Team.objects.create(
            name='Rival Team Senior', category=self.category, federation_id='TEAM-2', is_active=True
        )
        self.other_team = Team.objects.create(
            name='Other Club Senior', category=self.category, club=self.other_club, federation_id='TEAM-3', is_active=True
        )

        self.season = Season.objects.resolve('2026-27')
        self.season.is_current = True
        self.season.save()

        self.league = League.objects.create(
            name='Superliga 2', federation_id='L-1', season=self.season, is_active=True, visibility_type='main', is_our_team_related=True
        )
        self.match_own = Match.objects.create(
            league=self.league, home_team=self.team, away_team=self.rival_team, match_date=timezone.now()
        )
        self.match_other = Match.objects.create(
            league=self.league, home_team=self.other_team, away_team=self.rival_team, match_date=timezone.now()
        )

        from ilovevoley.competitions.models import MatchChangeLog
        self.log_own = MatchChangeLog.objects.create(
            match=self.match_own,
            change_type='datetime',
            field_name='match_date',
            old_value='01/10/2026 10:00',
            new_value='01/10/2026 12:00',
            is_last_minute=True,
        )
        self.log_other = MatchChangeLog.objects.create(
            match=self.match_other,
            change_type='venue',
            field_name='venue',
            old_value='Pista 1',
            new_value='Pista 2',
            is_last_minute=True,
        )

    def test_regular_member_forbidden(self):
        self.client.force_login(self.regular_member)
        url = reverse('competitions:match_changes_review')
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 403)

    def test_manager_sees_own_changes_only(self):
        self.client.force_login(self.manager_user)
        url = reverse('competitions:match_changes_review')
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        changes = response.context['changes']
        self.assertIn(self.log_own, changes)
        self.assertNotIn(self.log_other, changes)

    def test_ajax_mark_change_reviewed(self):
        self.client.force_login(self.manager_user)
        url = reverse('competitions:ajax_mark_change_reviewed', kwargs={'log_id': self.log_own.id})
        response = self.client.post(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status'), 'success')
        self.assertTrue(data.get('reviewed'))

        self.log_own.refresh_from_db()
        self.assertTrue(self.log_own.reviewed)
        self.assertEqual(self.log_own.reviewed_by, self.manager_user)
        self.assertIsNotNone(self.log_own.reviewed_at)

    def test_ajax_mark_change_reviewed_other_tenant_404(self):
        self.client.force_login(self.manager_user)
        # Intentar marcar un cambio que pertenece a otro tenant
        url = reverse('competitions:ajax_mark_change_reviewed', kwargs={'log_id': self.log_other.id})
        response = self.client.post(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 404)

    def test_org_without_linked_club_sees_no_changes(self):
        """Una organización sin club federado no debe ver cambios de otros clubes.

        Antes de #200, ``MatchChangeLogQuerySet.for_tenant`` devolvía ``self.all()``
        cuando ``get_tenant_club(tenant)`` era None, filtrando el panel completo.
        """
        User = get_user_model()
        from ilovevoley.users.models import Membership
        noclub_org = Organization.objects.create(slug='noclub', name='Sin Club', is_active=True)
        manager = User.objects.create_user(username='noclub_manager', email='manager@noclub.es')
        Membership.objects.create(
            user=manager, organization=noclub_org, role='manager', is_approved=True
        )

        self.client.force_login(manager)
        url = reverse('competitions:match_changes_review')
        response = self.client.get(url, HTTP_HOST='noclub.ilovevoley.es')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['changes']), [])



