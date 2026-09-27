from io import BytesIO
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from PIL import Image

from ilovevoley.competitions import result_card
from ilovevoley.core.security import UnsafeURL


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

    def test_logo_fetcher_failure_still_returns_png(self):
        match = _fake_match()
        match.home_team.display_logo = 'https://logos.example/home.png'
        match.away_team.display_logo = 'https://logos.example/away.png'

        def failing_fetcher(url):
            raise OSError(f'falló la descarga de {url}')

        png = result_card.render_result_card(
            match=match,
            organization=_fake_org(),
            logo_fetcher=failing_fetcher,
        )

        self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')


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
            result_card.extract_set_scores(lineup, 'CV Haris', 'CV Guaguas'),
            [(25, 21)],
        )


class FetchLogoBytesTests(SimpleTestCase):
    @override_settings(ACTA_ALLOWED_HOSTS=['logos.example'])
    @patch('ilovevoley.competitions.result_card.safe_get')
    def test_uses_safe_get_with_allowed_hosts(self, safe_get):
        safe_get.return_value = b'logo bytes'

        logo = result_card.fetch_logo_bytes(
            'https://logos.example/crest.png', timeout=3
        )

        self.assertEqual(logo, b'logo bytes')
        safe_get.assert_called_once_with(
            'https://logos.example/crest.png',
            allowed_hosts=['logos.example'],
            timeout=3,
            max_bytes=2 * 1024 * 1024,
        )

    @patch('ilovevoley.competitions.result_card.safe_get')
    def test_returns_none_when_download_fails(self, safe_get):
        for error in (UnsafeURL('host no permitido'), OSError('red caída')):
            with self.subTest(error=type(error).__name__):
                safe_get.reset_mock()
                safe_get.side_effect = error

                self.assertIsNone(
                    result_card.fetch_logo_bytes('https://logos.example/crest.png')
                )
