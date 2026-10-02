from unittest.mock import MagicMock

from django.test import SimpleTestCase
from django.utils import timezone

from ilovevoley.competitions.services.sets import extract_set_scores, match_set_scores


def _fake_match(**overrides):
    m = MagicMock()
    m.id = 42
    m.home_score = 3
    m.away_score = 1
    m.home_team_display = 'Local CV'
    m.away_team_display = 'Visitante VC'
    m.match_date = timezone.now()
    m.league = MagicMock()
    m.league.name = 'Liga Test'
    m.home_team = MagicMock()
    m.home_team.display_logo = None
    m.away_team = MagicMock()
    m.away_team.display_logo = None
    for k, v in overrides.items():
        setattr(m, k, v)
    return m


class ExtractSetScoresTests(SimpleTestCase):
    def test_maps_points_by_team_name(self):
        lineup = {
            'sets': [
                {
                    'teams': [
                        {'name': 'Local CV A', 'points': 25},
                        {'name': 'Visitante VC B', 'points': 20},
                    ]
                },
                {
                    'teams': [
                        {'name': 'Visitante VC B', 'points': 22},
                        {'name': 'Local CV A', 'points': 25},
                    ]
                },
            ]
        }
        scores = extract_set_scores(
            lineup, home_name='Local CV A', away_name='Visitante VC B'
        )
        self.assertEqual(scores, [(25, 20), (25, 22)])

    def test_skips_sets_without_points(self):
        lineup = {
            'sets': [
                {'teams': [{'name': 'A', 'points': None}, {'name': 'B', 'points': 20}]},
            ]
        }
        self.assertEqual(
            extract_set_scores(lineup, 'A', 'B'),
            [],
        )

    def test_assigns_shared_prefix_to_team_with_best_name_match(self):
        lineup = {
            'sets': [
                {
                    'teams': [
                        {'name': 'CV Haris', 'points': 25},
                        {'name': 'CV Guaguas', 'points': 21},
                    ]
                },
            ]
        }

        self.assertEqual(
            extract_set_scores(lineup, 'CV Haris', 'CV Guaguas'),
            [(25, 21)],
        )


class MatchSetScoresTests(SimpleTestCase):
    """Precedencia: el acta manda; si no aporta parciales, se usan set_scores."""

    def test_acta_takes_precedence(self):
        match = _fake_match(
            acta_data={
                'sets': [
                    {'teams': [
                        {'name': 'Local CV', 'points': 25},
                        {'name': 'Visitante VC', 'points': 20},
                    ]},
                ]
            },
            set_scores=[[25, 0], [25, 0], [25, 0]],
        )
        self.assertEqual(match_set_scores(match), [(25, 20)])

    def test_falls_back_to_set_scores_without_acta(self):
        match = _fake_match(acta_data=None, set_scores=[[25, 20], [20, 25], [25, 23]])
        self.assertEqual(match_set_scores(match), [(25, 20), (20, 25), (25, 23)])

    def test_falls_back_when_acta_has_no_points(self):
        match = _fake_match(acta_data={'sets': []}, set_scores=[[25, 20], [25, 18], [25, 22]])
        self.assertEqual(match_set_scores(match), [(25, 20), (25, 18), (25, 22)])

    def test_empty_when_nothing_available(self):
        match = _fake_match(acta_data=None, set_scores=None)
        self.assertEqual(match_set_scores(match), [])
