from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import RequestFactory, TestCase
from django.utils import timezone

from ilovevoley.competitions.calendar_feed import UserMatchesFeed
from ilovevoley.competitions.models import Match, Venue
from ilovevoley.users.models import User


class CalendarFeedLocationTest(TestCase):
    """Calendar de iOS solo muestra mapa y trayecto con coordenadas (#267)."""

    def _render(self, venue):
        user = User.objects.create_user(username='u', password='x')
        match = Match.objects.create(match_date=timezone.now(), venue_ref=venue)
        request = RequestFactory().get('/')
        with patch.object(UserMatchesFeed, 'items', lambda self, obj: [match]):
            response = UserMatchesFeed()(request, token=user.calendar_token)
        return response.content.decode().replace('\r\n ', '')

    def test_venue_with_coordinates_emits_geo_and_apple_location(self):
        venue = Venue.objects.create(
            name="Pavelló d'Alaró", address='Camí Vell d\'Orient s/n', city='Alaró',
            latitude=Decimal('39.698457'), longitude=Decimal('2.802078'),
        )
        ics = self._render(venue)
        self.assertIn('GEO:39.698457;2.802078', ics)
        self.assertIn('geo:39.698457,2.802078', ics)
        self.assertIn('X-APPLE-STRUCTURED-LOCATION;', ics)
        self.assertIn('LOCATION:', ics)
        self.assertIn('https://www.google.com/maps/search/?api=1&query=39.698457', ics)
        self.assertIn('2.802078', ics)

    def test_venue_without_coordinates_keeps_plain_location_only(self):
        venue = Venue.objects.create(name='Pavelló Sin Coordenadas', address='Carrer Major 1', city='Campos')
        ics = self._render(venue)
        self.assertNotIn('GEO:', ics)
        self.assertNotIn('X-APPLE-STRUCTURED-LOCATION', ics)
        self.assertIn('LOCATION:Pavelló Sin Coordenadas', ics)


class CalendarFeedFollowedTeamsTest(TestCase):
    """En cada club, los equipos seguidos sustituyen a las categorías; sin equipos, sigue por categoría (#363)."""

    def test_multi_club_user_gets_followed_teams_in_one_club_and_categories_in_the_other(self):
        from ilovevoley.competitions.models import League
        from ilovevoley.core.models import Category, Organization
        from ilovevoley.teams.models import Club, Team
        from ilovevoley.users.models import CategoryPreference, Membership

        cadete = Category.objects.create(name='Cadete')
        league = League.objects.create(name='Lliga Cadet', federation_id='l-cad')
        league.categories.set([cadete])
        club_a = Club.objects.create(federation_id='c-a', official_name='Club A')
        club_b = Club.objects.create(federation_id='c-b', official_name='Club B')
        org_a = Organization.objects.create(name='Club A', slug='club-a', club=club_a)
        org_b = Organization.objects.create(name='Club B', slug='club-b', club=club_b)
        a_cadete_a = Team.objects.create(name='A Cadete A', federation_id='t-aa', club=club_a)
        a_cadete_b = Team.objects.create(name='A Cadete B', federation_id='t-ab', club=club_a)
        b_cadete = Team.objects.create(name='B Cadete', federation_id='t-b', club=club_b)
        rival = Team.objects.create(name='Rival', federation_id='t-r')

        user = User.objects.create_user(username='u', password='x')
        for org in (org_a, org_b):
            Membership.objects.create(user=user, organization=org, is_approved=True)
        pref_a = CategoryPreference.objects.create(user=user, organization=org_a)
        pref_a.categories.set([cadete])
        pref_a.teams.set([a_cadete_b])
        CategoryPreference.objects.create(user=user, organization=org_b).categories.set([cadete])

        def match(home):
            return Match.objects.create(
                match_date=timezone.now() + timedelta(days=1), home_team=home, away_team=rival, league=league,
            )
        followed, not_followed, other_club = match(a_cadete_b), match(a_cadete_a), match(b_cadete)

        items = set(UserMatchesFeed().items(user))

        self.assertEqual(items, {followed, other_club})
