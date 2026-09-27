from io import BytesIO
from unittest.mock import MagicMock

from django.test import SimpleTestCase
from django.utils import timezone
from PIL import Image

from ilovevoley.competitions import result_card


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


def _fake_org(**overrides):
    o = MagicMock()
    o.name = 'Test Org'
    o.primary_color = '#C8102E'
    o.secondary_color = '#7B5FA0'
    o.logo = False  # truthy check: no logo file
    for k, v in overrides.items():
        setattr(o, k, v)
    return o


class RenderResultCardTests(SimpleTestCase):
    def test_square_png_dimensions(self):
        png = result_card.render_result_card(
            match=_fake_match(),
            organization=_fake_org(),
            card_format='square',
            sets=[],
            logo_fetcher=lambda url: None,
        )
        img = Image.open(BytesIO(png))
        self.assertEqual(img.format, 'PNG')
        self.assertEqual(img.size, (1080, 1080))

    def test_story_png_dimensions(self):
        png = result_card.render_result_card(
            match=_fake_match(),
            organization=_fake_org(),
            card_format='story',
            sets=[(25, 20), (22, 25), (25, 18), (25, 21)],
            logo_fetcher=lambda url: None,
        )
        img = Image.open(BytesIO(png))
        self.assertEqual(img.size, (1080, 1920))

    def test_without_logos_still_returns_png(self):
        png = result_card.render_result_card(
            match=_fake_match(),
            organization=_fake_org(),
            card_format='square',
            sets=None,
            logo_fetcher=lambda url: None,
        )
        self.assertTrue(png[:8] == b'\x89PNG\r\n\x1a\n')


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
        scores = result_card.extract_set_scores(
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
            result_card.extract_set_scores(lineup, 'A', 'B'),
            [],
        )
