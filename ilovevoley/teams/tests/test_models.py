from django.test import TestCase

from ilovevoley.competitions.models import Venue
from ilovevoley.teams.models import Club


class ClubModelTest(TestCase):
    def test_club_default_venue_relation(self):
        venue = Venue.objects.create(name="Pavelló Test Blanquerna Unique", city="Marratxí")
        club = Club.objects.create(
            federation_id="999-TEST",
            official_name="Club Voleibol Pòrtol Test",
            default_venue=venue
        )
        self.assertEqual(club.default_venue, venue)
        self.assertIn(club, venue.clubs.all())
