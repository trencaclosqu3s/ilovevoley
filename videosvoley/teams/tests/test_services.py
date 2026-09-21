from django.test import SimpleTestCase

from videosvoley.teams.services import MATCH_THRESHOLD, find_best_club


class _FakeClub:
    def __init__(self, official_name):
        self.official_name = official_name


class ClubMatchingTest(SimpleTestCase):
    """El matcher decide a qué club se asignan equipos huérfanos."""

    def test_matches_team_with_sponsor_to_official_name(self):
        club = _FakeClub('CLUB ESPORTIU SANT JOSEP OBRER')
        match = find_best_club('SANT JOSEP OBRER', [club])
        self.assertIsNotNone(match)
        self.assertIs(match[0], club)
        self.assertGreaterEqual(match[1], MATCH_THRESHOLD)

    def test_unrelated_name_stays_below_threshold(self):
        club = _FakeClub('CLUB ESPORTIU SANT JOSEP OBRER')
        match = find_best_club('CV ALTRES ESCOLA', [club])
        self.assertTrue(match is None or match[1] < MATCH_THRESHOLD)

    def test_picks_best_among_several_clubs(self):
        other = _FakeClub('CLUB VOLEIBOL SOLLER')
        target = _FakeClub('CLUB ESPORTIU SANT JOSEP OBRER')
        match = find_best_club('SANT JOSEP OBRER', [other, target])
        self.assertIs(match[0], target)
