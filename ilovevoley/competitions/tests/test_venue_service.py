from django.test import TestCase
from django.utils import timezone

from ilovevoley.competitions.models import Match, Venue
from ilovevoley.competitions.services.venue_service import get_match_location_info
from ilovevoley.teams.models import Club, Team


class VenueServiceTest(TestCase):
    def setUp(self):
        self.venue_soller = Venue.objects.create(
            name="Pav. Son Angelats",
            address="Carretera a Deià, s/n",
            city="Sóller",
            google_maps_url="https://maps.app.goo.gl/soller",
            aliases="Poliesportiu Son Angelats"
        )
        self.venue_mayurqa = Venue.objects.create(
            name="Pav. Col. Sta. Magdalena Sofia",
            address="Carrer de Francesc Martí i Móra, 42",
            city="Palma",
            google_maps_url="https://maps.app.goo.gl/mayurqa"
        )
        self.club_mayurqa = Club.objects.create(
            federation_id="100",
            official_name="CV Mayurqa",
            default_venue=self.venue_mayurqa
        )
        self.team_mayurqa = Team.objects.create(
            federation_id="100-1",
            name="Voley Palma Mayurqa",
            club=self.club_mayurqa
        )

    def test_priority_1_direct_venue_ref(self):
        match = Match.objects.create(
            match_date=timezone.now(),
            venue_ref=self.venue_soller,
            home_team=self.team_mayurqa
        )
        info = get_match_location_info(match)
        self.assertEqual(info['venue'], self.venue_soller)
        self.assertEqual(info['location_text'], self.venue_soller.full_address)
        self.assertEqual(info['maps_url'], "https://maps.app.goo.gl/soller")
        self.assertFalse(info['is_inferred'])

    def test_priority_2_match_venue_text_overrides_home_club_default(self):
        # Caso real: Mayurqa juega de local pero en Sóller (Son Angelats)
        match = Match.objects.create(
            match_date=timezone.now(),
            venue="Pav. Son Angelats",
            home_team=self.team_mayurqa
        )
        info = get_match_location_info(match)
        self.assertEqual(info['venue'], self.venue_soller)
        self.assertEqual(info['location_text'], self.venue_soller.full_address)
        self.assertEqual(info['maps_url'], "https://maps.app.goo.gl/soller")
        self.assertFalse(info['is_inferred'])

    def test_priority_3_fallback_to_home_club_default_when_venue_empty(self):
        # Partido sin datos de pista en federación
        match = Match.objects.create(
            match_date=timezone.now(),
            venue="",
            city="",
            home_team=self.team_mayurqa
        )
        info = get_match_location_info(match)
        self.assertEqual(info['venue'], self.venue_mayurqa)
        self.assertEqual(info['location_text'], self.venue_mayurqa.full_address)
        self.assertEqual(info['maps_url'], "https://maps.app.goo.gl/mayurqa")
        self.assertTrue(info['is_inferred'])

    def test_priority_4_fallback_to_match_raw_text(self):
        # Partido en pabellón no registrado en Venue
        match = Match.objects.create(
            match_date=timezone.now(),
            venue="Polideportivo Desconocido",
            field_address="Calle Mayor 1",
            city="Inca"
        )
        info = get_match_location_info(match)
        self.assertIsNone(info['venue'])
        self.assertEqual(info['location_text'], "Polideportivo Desconocido, Calle Mayor 1, Inca")
        self.assertIn("https://www.google.com/maps/search/?api=1&query=", info['maps_url'])
        self.assertFalse(info['is_inferred'])

    def test_fallback_when_completely_empty(self):
        match = Match.objects.create(
            match_date=timezone.now(),
            venue="",
            field_address="",
            city=""
        )
        info = get_match_location_info(match)
        self.assertIsNone(info['venue'])
        self.assertEqual(info['location_text'], "Por confirmar")
        self.assertIsNone(info['maps_url'])
        self.assertFalse(info['is_inferred'])
