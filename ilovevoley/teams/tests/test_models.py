from django.test import TestCase

from ilovevoley.competitions.models import Venue
from ilovevoley.core.models import GENDER_FEMALE, GENDER_MALE, Category
from ilovevoley.teams.models import Club, Team


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


class TeamEffectiveGenderTest(TestCase):
    def setUp(self):
        self.club = Club.objects.create(federation_id='gender-club', official_name='Club Gender')

    def test_own_gender_wins_over_category(self):
        category = Category.objects.create(name='Senior M gender', gender=GENDER_MALE)
        team = Team.objects.create(
            name='Team Own', federation_id='gender-t1', club=self.club,
            category=category, gender=GENDER_FEMALE,
        )
        self.assertEqual(team.effective_gender, GENDER_FEMALE)

    def test_inherits_from_category_and_defaults_to_blank(self):
        category = Category.objects.create(name='Senior F gender', gender=GENDER_FEMALE)
        team = Team.objects.create(
            name='Team Inherit', federation_id='gender-t2', club=self.club, category=category,
        )
        self.assertEqual(team.effective_gender, GENDER_FEMALE)

        empty = Team.objects.create(name='Team Empty', federation_id='gender-t3', club=self.club)
        self.assertEqual(empty.effective_gender, '')
