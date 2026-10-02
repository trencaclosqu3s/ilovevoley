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
