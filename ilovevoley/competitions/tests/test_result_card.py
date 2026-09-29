from datetime import datetime, timezone as dt_timezone
from io import BytesIO
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from PIL import Image, ImageDraw

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


def _fake_photo_bytes() -> bytes:
    buffer = BytesIO()
    Image.new('RGB', (800, 600), (30, 60, 90)).save(buffer, format='JPEG')
    return buffer.getvalue()


def _capture_drawn_text():
    """Espía las llamadas a draw.text() conservando el dibujado real."""
    calls = []
    real_draw = ImageDraw.Draw

    def factory(image, *args, **kwargs):
        draw = real_draw(image, *args, **kwargs)
        original = draw.text

        def text(xy, content, *t_args, **t_kwargs):
            calls.append((xy, content, t_kwargs.get('font')))
            return original(xy, content, *t_args, **t_kwargs)

        draw.text = text
        return draw

    return calls, patch.object(result_card.ImageDraw, 'Draw', side_effect=factory)


class RenderResultCardTests(SimpleTestCase):
    def test_date_is_rendered_in_local_timezone(self):
        # 31/05 22:30 UTC son ya las 00:30 del 01/06 en Europe/Madrid.
        match = _fake_match(
            match_date=datetime(2026, 5, 31, 22, 30, tzinfo=dt_timezone.utc)
        )
        calls, spy = _capture_drawn_text()

        with spy:
            result_card.render_result_card(
                match=match,
                organization=_fake_org(),
                sets=[],
                logo_fetcher=lambda url: None,
            )

        drawn = [content for _, content, _ in calls]
        self.assertIn('01/06/2026', drawn)
        self.assertNotIn('31/05/2026', drawn)

    def test_long_team_names_do_not_overlap(self):
        match = _fake_match(
            home_team_display='Club Voleibol Universitario de Las Palmas de Gran Canaria',
            away_team_display='Agrupación Deportiva Voleibol Sanaya Libby\'s La Laguna',
        )
        calls, spy = _capture_drawn_text()

        with spy:
            result_card.render_result_card(
                match=match,
                organization=_fake_org(),
                sets=[],
                logo_fetcher=lambda url: None,
            )

        truncated = [call for call in calls if call[1].endswith('…')]
        self.assertEqual(len(truncated), 2, calls)

        measure = ImageDraw.Draw(Image.new('RGB', (10, 10)))
        home_call, away_call = truncated
        home_end = home_call[0][0] + result_card._text_width(
            measure, home_call[1], home_call[2]
        )

        self.assertLess(home_end, away_call[0][0])

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

    def test_marco_style_requires_photo(self):
        with self.assertRaises(ValueError):
            result_card.render_result_card(
                match=_fake_match(),
                organization=_fake_org(),
                card_style='marco',
                photo=None,
                logo_fetcher=lambda url: None,
            )

    def test_invalid_card_style_raises(self):
        with self.assertRaises(ValueError):
            result_card.render_result_card(
                match=_fake_match(),
                organization=_fake_org(),
                card_style='inventado',
                logo_fetcher=lambda url: None,
            )

    def test_marco_style_with_photo_and_sets_returns_png(self):
        png = result_card.render_result_card(
            match=_fake_match(),
            organization=_fake_org(),
            card_format='story',
            card_style='marco',
            photo=_fake_photo_bytes(),
            sets=[(25, 20), (18, 25), (25, 22)],
            logo_fetcher=lambda url: None,
        )
        img = Image.open(BytesIO(png))
        self.assertEqual(img.format, 'PNG')
        self.assertEqual(img.size, (1080, 1920))

    def test_marco_style_without_sets_still_returns_png(self):
        png = result_card.render_result_card(
            match=_fake_match(),
            organization=_fake_org(),
            card_style='marco',
            photo=_fake_photo_bytes(),
            sets=[],
            logo_fetcher=lambda url: None,
        )
        self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')

    def test_marco_style_falls_back_to_gradient_on_invalid_photo(self):
        png = result_card.render_result_card(
            match=_fake_match(),
            organization=_fake_org(),
            card_style='marco',
            photo=b'esto no es una imagen',
            logo_fetcher=lambda url: None,
        )
        self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')

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


class PasteCrestCircleTests(SimpleTestCase):
    def test_clips_rectangular_crest_to_circle(self):
        """Un escudo cuadrado opaco no debe sobresalir del disco (issue #241)."""
        size = 100
        crest = Image.new('RGBA', (size, size), (10, 20, 30, 255))
        base = Image.new('RGBA', (size, size), (200, 200, 200, 255))

        result_card._paste_crest_circle(base, crest, size, 0, 0)

        corner = base.getpixel((2, 2))
        self.assertEqual(corner[:3], (200, 200, 200))
        center = base.getpixel((size // 2, size // 2))
        self.assertEqual(center[:3], (10, 20, 30))


class DrawBackgroundBlobsTests(SimpleTestCase):
    def test_blobs_lighten_and_darken_the_flat_background(self):
        """El fondo 'completa' no debe quedar liso: lleva manchas difuminadas (issue #241)."""
        width, height = 400, 400
        base = Image.new('RGB', (width, height), (100, 100, 100))
        metrics = {'blob_top': (200, -50, -50), 'blob_bottom': (200, 50, 50)}

        result_card._draw_background_blobs(base, width, height, metrics)

        top_left = base.getpixel((10, 10))
        bottom_right = base.getpixel((width - 10, height - 10))
        flat_area = base.getpixel((width // 2, height // 2))

        self.assertEqual(flat_area, (100, 100, 100))
        self.assertGreater(sum(top_left), sum(flat_area))
        self.assertLess(sum(bottom_right), sum(flat_area))


class DitherTests(SimpleTestCase):
    def test_breaks_up_flat_gradient_banding(self):
        """Un degradado de 8 bits sin ruido deja bandas de color visibles a tamaño real (#241)."""
        width, height = 40, 400
        seed = Image.new('RGB', (1, 2), (109, 76, 145))
        seed.putpixel((0, 1), (155, 127, 191))
        plain = seed.resize((width, height), Image.Resampling.BILINEAR)

        dithered = result_card._dither(plain)

        column = [plain.getpixel((width // 2, y)) for y in range(height)]
        dithered_column = [dithered.getpixel((width // 2, y)) for y in range(height)]

        def longest_run(values):
            best = current = 1
            for a, b in zip(values, values[1:]):
                current = current + 1 if a == b else 1
                best = max(best, current)
            return best

        self.assertGreater(longest_run(column), 10, 'el degradado de prueba no tenía banding')
        self.assertLess(longest_run(dithered_column), 10)
