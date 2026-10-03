from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ilovevoley.competitions.models import League, Match, Venue
from ilovevoley.competitions.services.where_plays import (
    search_locations,
    search_team_locations,
    search_venues,
)
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.teams.models import Club, Team


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es'])
class WherePlaysServiceTests(TestCase):
    """Búsqueda pública por equipo/club acotada a las ligas del tenant."""

    def setUp(self):
        cache.clear()
        self.season = Season.objects.resolve('2026-2027')
        self.venue = Venue.objects.create(
            name='Pav. Son Angelats', address='Carretera a Deià, s/n', city='Sóller',
            google_maps_url='https://maps.app.goo.gl/soller',
        )
        self.default_venue = Venue.objects.create(
            name='Pav. Municipal Inca', address='Carrer Major 1', city='Inca',
            google_maps_url='https://maps.app.goo.gl/inca',
        )

        self.org = Organization.objects.create(slug='testclub', name='Test Club', is_active=True)
        self.other_org = Organization.objects.create(slug='rivalclub', name='Rival Club', is_active=True)
        self.club = Club.objects.create(
            official_name='Club Test', federation_id='CLUB-A', default_venue=self.default_venue,
        )
        self.other_club = Club.objects.create(official_name='CV Mayurqa', federation_id='CLUB-B')
        self.org.club = self.club
        self.org.save(update_fields=['club'])
        self.other_org.club = self.other_club
        self.other_org.save(update_fields=['club'])

        self.category = Category.objects.create(name='Senior', is_active=True)
        self.team = Team.objects.create(
            name='Test Senior', category=self.category, club=self.club,
            federation_id='TEAM-A1', is_active=True,
        )
        self.team_without_matches = Team.objects.create(
            name='Test Cadete', category=self.category, club=self.club,
            federation_id='TEAM-A2', is_active=True,
        )
        self.rival = Team.objects.create(
            name='Mayurqa Senior', category=self.category, club=self.other_club,
            federation_id='TEAM-B1', is_active=True,
        )
        self.foreign = Team.objects.create(
            name='Extranjero Senior', category=self.category, club=None,
            federation_id='TEAM-C1', is_active=True,
        )

        self.league = League.objects.create(
            name='Liga Propia', federation_id='LEAGUE-A', season=self.season,
            is_active=True, visibility_type='main', is_our_team_related=True,
        )
        self.league.categories.add(self.category)
        self.other_league = League.objects.create(
            name='Liga Ajena', federation_id='LEAGUE-B', season=self.season,
            is_active=True, visibility_type='main', is_our_team_related=True,
        )

        self.upcoming = Match.objects.create(
            league=self.league, home_team=self.rival, away_team=self.team,
            match_date=timezone.now() + timedelta(days=3),
            venue_ref=self.venue, round_number=1, status='scheduled',
        )
        # 'Test Cadete' está en la liga del tenant pero solo con partidos ya jugados.
        Match.objects.create(
            league=self.league, home_team=self.team_without_matches, away_team=self.team,
            match_date=timezone.now() - timedelta(days=10),
            round_number=9, status='finished',
        )
        # Partido de un club ajeno en una liga ajena: no debe asomar en el tenant.
        Match.objects.create(
            league=self.other_league, home_team=self.rival, away_team=self.foreign,
            match_date=timezone.now() + timedelta(days=4), round_number=1, status='scheduled',
        )

    def test_finds_team_and_resolves_match_venue(self):
        results = search_team_locations(self.org, 'Mayurqa')
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result['team_name'], 'Mayurqa Senior')
        self.assertEqual(result['club_name'], 'CV Mayurqa')
        self.assertEqual(len(result['matches']), 1)
        match = result['matches'][0]
        self.assertEqual(match['location_text'], self.venue.full_address)
        self.assertEqual(match['maps_url'], 'https://maps.app.goo.gl/soller')
        self.assertTrue(match['is_home'])
        self.assertIsNone(result['default_venue'])

    def test_query_below_min_length_returns_nothing(self):
        self.assertEqual(search_team_locations(self.org, 'Ma'), [])

    def test_team_without_upcoming_match_falls_back_to_default_venue(self):
        results = search_team_locations(self.org, 'Test Cadete')
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result['matches'], [])
        self.assertEqual(result['default_venue']['name'], 'Pav. Municipal Inca')
        self.assertEqual(result['default_venue']['maps_url'], 'https://maps.app.goo.gl/inca')

    def test_ignores_teams_outside_tenant_leagues(self):
        self.assertEqual(search_team_locations(self.org, 'Extranjero'), [])

    def test_withdrawn_match_is_not_offered(self):
        other = Match.objects.create(
            league=self.league, home_team=self.team, away_team=self.rival,
            match_date=timezone.now() + timedelta(days=6), round_number=2, status='scheduled',
        )
        self.upcoming.status = 'withdrawn'
        self.upcoming.save(update_fields=['status'])
        results = search_team_locations(self.org, 'Mayurqa')
        offered_ids = [m['id'] for m in results[0]['matches']]
        self.assertNotIn(self.upcoming.id, offered_ids)
        self.assertIn(other.id, offered_ids)

    def test_por_confirmar_has_no_broken_link(self):
        match = Match.objects.create(
            league=self.league, home_team=self.rival, away_team=self.team,
            match_date=timezone.now() + timedelta(days=5),
            venue='', field_address='', city='', round_number=2, status='scheduled',
        )
        results = search_team_locations(self.org, 'Mayurqa')
        payload = next(p for p in results[0]['matches'] if p['id'] == match.id)
        self.assertEqual(payload['location_text'], 'Por confirmar')
        self.assertIsNone(payload['maps_url'])


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es'])
class VenueSearchServiceTests(TestCase):
    """Búsqueda directa de pabellones por nombre, alias o municipio."""

    def setUp(self):
        cache.clear()
        self.season = Season.objects.resolve('2026-2027')
        self.org = Organization.objects.create(slug='testclub', name='Test Club', is_active=True)
        self.club = Club.objects.create(official_name='Club Test', federation_id='CLUB-A')
        self.org.club = self.club
        self.org.save(update_fields=['club'])
        self.category = Category.objects.create(name='Senior', is_active=True)
        self.team = Team.objects.create(
            name='Test Senior', category=self.category, club=self.club,
            federation_id='TEAM-A1', is_active=True,
        )
        self.rival = Team.objects.create(
            name='Mayurqa Senior', category=self.category, club=None,
            federation_id='TEAM-B1', is_active=True,
        )
        self.venue = Venue.objects.create(
            name='Pav. Test Ciutatprova', short_name='Test Ciutatprova',
            address='Carrer de la Prova, 1', city='Ciutatprova',
            aliases='Pavelló Test Alias, Pista Test',
            google_maps_url='https://maps.app.goo.gl/ciutatprova',
        )
        self.league = League.objects.create(
            name='Liga Propia', federation_id='LEAGUE-A', season=self.season,
            is_active=True, visibility_type='main', is_our_team_related=True,
        )
        self.league.categories.add(self.category)
        self.match = Match.objects.create(
            league=self.league, home_team=self.rival, away_team=self.team,
            match_date=timezone.now() + timedelta(days=3), venue_ref=self.venue,
            round_number=1, status='scheduled',
        )

    def test_finds_venue_by_name(self):
        results = search_venues(self.org, 'Pav. Test Ciutatprova')
        self.assertEqual(len(results), 1)
        venue = results[0]
        self.assertEqual(venue['type'], 'venue')
        self.assertEqual(venue['name'], 'Pav. Test Ciutatprova')
        self.assertEqual(venue['city'], 'Ciutatprova')
        self.assertEqual(venue['maps_url'], 'https://maps.app.goo.gl/ciutatprova')
        self.assertEqual([m['id'] for m in venue['matches']], [self.match.id])

    def test_finds_venue_by_city(self):
        results = search_venues(self.org, 'Ciutatprova')
        self.assertEqual([v['name'] for v in results], ['Pav. Test Ciutatprova'])

    def test_finds_venue_by_alias(self):
        results = search_venues(self.org, 'Pavelló Test Alias')
        self.assertEqual([v['name'] for v in results], ['Pav. Test Ciutatprova'])

    def test_venue_matches_are_scoped_to_tenant_leagues(self):
        other_league = League.objects.create(
            name='Liga Ajena', federation_id='LEAGUE-B', season=self.season,
            is_active=True, visibility_type='main', is_our_team_related=True,
        )
        foreign = Team.objects.create(
            name='Extranjero Senior', category=self.category, club=None,
            federation_id='TEAM-C1', is_active=True,
        )
        Match.objects.create(
            league=other_league, home_team=self.rival, away_team=foreign,
            match_date=timezone.now() + timedelta(days=4), venue_ref=self.venue,
            round_number=1, status='scheduled',
        )
        results = search_venues(self.org, 'Ciutatprova')
        self.assertEqual([m['id'] for m in results[0]['matches']], [self.match.id])

    def test_search_locations_combines_teams_and_venues(self):
        self.assertTrue(all(r['type'] == 'venue' for r in search_locations(self.org, 'Ciutatprova')))
        results = search_locations(self.org, 'Test Senior')
        self.assertTrue(all(r['type'] == 'team' for r in results))

    def test_venue_matches_resolved_in_single_query(self):
        """Los próximos partidos de todas las sedes se cargan en una sola query,
        no una por sede (endpoint público en vivo)."""
        extra = Venue.objects.create(name='Pav. Test Altre', city='Ciutatprova')
        Match.objects.create(
            league=self.league, home_team=self.team, away_team=self.rival,
            match_date=timezone.now() + timedelta(days=5), venue_ref=extra,
            round_number=2, status='scheduled',
        )
        with self.assertNumQueries(6):
            search_venues(self.org, 'Ciutatprova')


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'ilovevoley.es'])
class WherePlaysViewTests(TestCase):
    """La página es pública (sin login) y se acota al tenant del subdominio."""

    def setUp(self):
        cache.clear()
        self.season = Season.objects.resolve('2026-2027')
        self.org = Organization.objects.create(slug='testclub', name='Test Club', is_active=True)
        self.club = Club.objects.create(official_name='Club Test', federation_id='CLUB-A')
        self.org.club = self.club
        self.org.save(update_fields=['club'])
        self.category = Category.objects.create(name='Senior', is_active=True)
        self.team = Team.objects.create(
            name='Test Senior', category=self.category, club=self.club,
            federation_id='TEAM-A1', is_active=True,
        )
        self.rival = Team.objects.create(
            name='Mayurqa Senior', category=self.category, club=None,
            federation_id='TEAM-B1', is_active=True,
        )
        self.venue = Venue.objects.create(name='Pav. Test Ciutatprova', address='Carrer 1', city='Ciutatprova')
        self.league = League.objects.create(
            name='Liga Propia', federation_id='LEAGUE-A', season=self.season,
            is_active=True, visibility_type='main', is_our_team_related=True,
        )
        self.league.categories.add(self.category)
        Match.objects.create(
            league=self.league, home_team=self.rival, away_team=self.team,
            match_date=timezone.now() + timedelta(days=3), venue_ref=self.venue,
            round_number=1, status='scheduled',
        )

    def test_public_access_without_login_renders_results(self):
        response = self.client.get(
            reverse('where_plays') + '?q=Mayurqa',
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mayurqa Senior')
        self.assertContains(response, 'Cómo llegar')

    def test_search_endpoint_returns_json(self):
        response = self.client.get(
            reverse('where_plays_search') + '?q=Mayurqa',
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['results'][0]['team_name'], 'Mayurqa Senior')
        self.assertTrue(payload['results'][0]['matches'][0]['maps_url'])

    def test_search_endpoint_returns_venue(self):
        response = self.client.get(
            reverse('where_plays_search') + '?q=Ciutatprova',
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['results'][0]['type'], 'venue')
        self.assertEqual(payload['results'][0]['name'], 'Pav. Test Ciutatprova')
        self.assertEqual(len(payload['results'][0]['matches']), 1)

    def test_page_renders_venue_card(self):
        response = self.client.get(
            reverse('where_plays') + '?q=Ciutatprova',
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pav. Test Ciutatprova')
        self.assertContains(response, 'Ciutatprova')
        self.assertContains(response, 'Cómo llegar')

    def test_search_endpoint_ignores_short_query(self):
        response = self.client.get(
            reverse('where_plays_search') + '?q=Ma',
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'], [])

    def test_root_domain_redirects_to_landing(self):
        response = self.client.get(reverse('where_plays'), HTTP_HOST='ilovevoley.es')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('landing'))
