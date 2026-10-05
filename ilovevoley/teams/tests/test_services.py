from django.test import TestCase
from django.utils import timezone

from ilovevoley.competitions.models import League, Match
from ilovevoley.core.models import Season
from ilovevoley.teams.models import Club, Team
from ilovevoley.teams.services import resolve_team_clubs


class ResolveTeamClubsTest(TestCase):
    """El club de un equipo sale de los ids de club de sus partidos, no del nombre (#380)."""

    def setUp(self):
        self.league = League.objects.create(
            name='Liga', federation_id='1', season=Season.objects.resolve('2026-27'),
            competition_type='regular', match_format='standard', visibility_type='main',
        )
        self.mataro = Club.objects.create(federation_id='10', official_name='CV MATARO')
        Club.objects.create(federation_id='20', official_name='CLUB MAYURQA')
        self.team = Team.objects.create(name='CV MATARO', federation_id='t1')
        self.rival = Team.objects.create(name='MAYURQA', federation_id='t2')

    def _match(self, home, away, home_club, away_club):
        Match.objects.create(
            league=self.league, home_team=home, away_team=away, match_date=timezone.now(),
            federation_club_local_id=home_club, federation_club_away_id=away_club,
        )

    def test_club_from_both_sides_of_its_matches(self):
        self._match(self.team, self.rival, '10', '20')
        self._match(self.rival, self.team, '20', '10')
        self._match(self.team, self.rival, 'None', '')

        self.assertEqual(resolve_team_clubs(Match, Club)[self.team.pk], self.mataro)

    def test_contradictory_club_ids_leave_team_without_club(self):
        self._match(self.team, self.rival, '10', '20')
        self._match(self.rival, self.team, '20', '20')

        self.assertNotIn(self.team.pk, resolve_team_clubs(Match, Club))
