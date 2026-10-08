from datetime import datetime, timezone as dt_timezone
from io import BytesIO
from unittest.mock import MagicMock, patch

from django.core.cache import cache
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
    m.home_team.display_logo_file = None
    m.away_team = MagicMock()
    m.away_team.display_logo = None
    m.away_team.display_logo_file = None
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


def _edge_photo(width, height, left, right, middle=(20, 20, 20)) -> bytes:
    """Foto con bandas de color en los extremos, para detectar recortes laterales."""
    image = Image.new('RGB', (width, height), middle)
    draw = ImageDraw.Draw(image)
    band = max(1, width // 8)
    draw.rectangle([0, 0, band, height], fill=left)
    draw.rectangle([width - band, 0, width, height], fill=right)
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


def _is_red(pixel) -> bool:
    r, g, b = pixel[:3]
    return r > 200 and g < 60 and b < 60


def _is_blue(pixel) -> bool:
    r, g, b = pixel[:3]
    return b > 200 and r < 60 and g < 60


def _is_green(pixel) -> bool:
    r, g, b = pixel[:3]
    return g > 200 and r < 60 and b < 60


def _is_magenta(pixel) -> bool:
    r, g, b = pixel[:3]
    return r > 200 and b > 200 and g < 60


def _is_dark(pixel) -> bool:
    r, g, b = pixel[:3]
    return r < 90 and g < 90 and b < 90


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

    def test_story_marco_panoramic_photo_is_not_side_cropped(self):
        """En Story la foto panorámica se encuadra entera, sin perder los laterales (#347)."""
        photo = _edge_photo(1600, 600, (255, 0, 0), (0, 0, 255))

        png = result_card.render_result_card(
            match=_fake_match(),
            organization=_fake_org(),
            card_format='story',
            card_style='marco',
            photo=photo,
            sets=[],
            logo_fetcher=lambda url: None,
        )
        img = Image.open(BytesIO(png))

        self.assertTrue(_is_red(img.getpixel((30, 959))), img.getpixel((30, 959)))
        self.assertTrue(_is_blue(img.getpixel((1049, 959))), img.getpixel((1049, 959)))

    def test_story_marco_vertical_photo_still_fills_width(self):
        """Una foto vertical sigue cubriendo el ancho completo, sin barras laterales (#347)."""
        photo = _edge_photo(600, 1600, (0, 255, 0), (255, 0, 255))

        png = result_card.render_result_card(
            match=_fake_match(),
            organization=_fake_org(),
            card_format='story',
            card_style='marco',
            photo=photo,
            sets=[],
            logo_fetcher=lambda url: None,
        )
        img = Image.open(BytesIO(png))

        self.assertTrue(_is_green(img.getpixel((30, 959))), img.getpixel((30, 959)))
        self.assertTrue(_is_magenta(img.getpixel((1049, 959))), img.getpixel((1049, 959)))

    def test_square_marco_panoramic_photo_keeps_cover_crop(self):
        """El formato 1:1 no cambia: la foto panorámica sigue recortada tipo cover (#347)."""
        photo = _edge_photo(1600, 600, (255, 0, 0), (0, 0, 255))

        png = result_card.render_result_card(
            match=_fake_match(),
            organization=_fake_org(),
            card_format='square',
            card_style='marco',
            photo=photo,
            sets=[],
            logo_fetcher=lambda url: None,
        )
        img = Image.open(BytesIO(png))

        self.assertTrue(_is_dark(img.getpixel((30, 300))), img.getpixel((30, 300)))
        self.assertTrue(_is_dark(img.getpixel((1049, 300))), img.getpixel((1049, 300)))

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

    def test_footer_renders_ilovevoley_es_in_completa_style(self):
        calls, spy = _capture_drawn_text()
        with spy:
            result_card.render_result_card(
                match=_fake_match(),
                organization=_fake_org(),
                card_style='completa',
                sets=[],
                logo_fetcher=lambda url: None,
            )
        drawn = [content for _, content, _ in calls]
        self.assertIn('ilovevoley.es', drawn)
        self.assertNotIn('ilovevoley', drawn)

    def test_footer_renders_ilovevoley_es_in_marco_style(self):
        calls, spy = _capture_drawn_text()
        with spy:
            result_card.render_result_card(
                match=_fake_match(),
                organization=_fake_org(),
                card_style='marco',
                photo=_fake_photo_bytes(),
                sets=[],
                logo_fetcher=lambda url: None,
            )
        drawn = [content for _, content, _ in calls]
        self.assertIn('ilovevoley.es', drawn)
        self.assertNotIn('ilovevoley', drawn)


class NormalizeLayoutTests(SimpleTestCase):
    def test_defaults_reproduce_classic_composition(self):
        layout = result_card.normalize_layout(None, 'story')
        metrics = result_card._FORMAT_METRICS['story']

        self.assertIsNone(layout['photo']['zoom'])
        self.assertIsNone(layout['score']['y'])
        self.assertEqual(layout['score']['scale'], 1.0)
        self.assertEqual(layout['gradients']['top']['alpha'], 190)
        self.assertEqual(layout['gradients']['bottom']['alpha'], 220)
        self.assertEqual(round(layout['gradients']['top']['height'] * 1920), metrics['scrim_top'])
        self.assertEqual(round(layout['gradients']['bottom']['height'] * 1920), metrics['scrim_bottom'])

    def test_out_of_range_and_invalid_values_are_clamped_or_defaulted(self):
        layout = result_card.normalize_layout(
            {
                'photo': {'zoom': 99, 'cx': -3, 'cy': 'x'},
                'score': {'scale': True, 'x': 5, 'y': 2},
                'gradients': {'top': {'color': 'rojo', 'alpha': 999}, 'bottom': 'basura'},
            },
            'square',
        )

        self.assertEqual(layout['photo'], {'zoom': 4.0, 'cx': 0, 'cy': 0.5})
        self.assertEqual(layout['score'], {'x': 1, 'y': 1, 'scale': 1.0})
        self.assertIsNone(layout['gradients']['top']['color'])
        self.assertEqual(layout['gradients']['top']['alpha'], 255)
        self.assertEqual(layout['gradients']['bottom']['alpha'], 220)


class CustomLayoutRenderTests(SimpleTestCase):
    def _render(self, layout, photo=None, card_format='square'):
        png = result_card.render_result_card(
            match=_fake_match(),
            organization=_fake_org(),
            card_format=card_format,
            card_style='marco',
            photo=photo or _fake_photo_bytes(),
            sets=[],
            layout=layout,
            logo_fetcher=lambda url: None,
        )
        return Image.open(BytesIO(png)).convert('RGB')

    def test_photo_zoom_keeps_proportion_and_follows_focus_point(self):
        photo = _edge_photo(1600, 600, (255, 0, 0), (0, 0, 255))

        left = self._render({'photo': {'zoom': 1, 'cx': 0}}, photo)
        contain = self._render({'photo': {'zoom': 0.1}}, photo)

        # Con zoom 1 y foco a la izquierda se ve el borde rojo y no el azul.
        self.assertTrue(_is_red(left.getpixel((30, 540))), left.getpixel((30, 540)))
        self.assertFalse(_is_blue(left.getpixel((1049, 540))))
        # Zoom mínimo = foto entera sin deformar: ambos bordes visibles.
        self.assertTrue(_is_red(contain.getpixel((30, 540))), contain.getpixel((30, 540)))
        self.assertTrue(_is_blue(contain.getpixel((1049, 540))), contain.getpixel((1049, 540)))

    def test_score_block_moves_to_requested_height(self):
        def brightness(img, y):
            box = img.crop((100, y - 5, 290, y + 5)).resize((1, 1), Image.Resampling.BOX)
            return sum(box.getpixel((0, 0)))

        default = self._render(None)
        moved = self._render({'score': {'y': 0.2}})

        # Escudos (disco blanco) arriba solo cuando se pide; por defecto van abajo.
        self.assertLess(brightness(default, 216), 300)
        self.assertGreater(brightness(moved, 216), 450)


class FooterAssetTests(SimpleTestCase):
    def test_isotype_asset_exists_and_is_valid_transparent_png(self):
        asset_path = result_card._LOGO_ISOTYPE
        self.assertTrue(asset_path.exists(), f'Falta el asset {asset_path}')
        with Image.open(asset_path) as img:
            self.assertEqual(img.format, 'PNG')
            self.assertEqual(img.mode, 'RGBA')
            alpha_extrema = img.getchannel('A').getextrema()
            self.assertEqual(alpha_extrema[0], 0, 'El icono debe tener fondo transparente')
            self.assertGreater(alpha_extrema[1], 0, 'El icono debe tener contenido visible')


class DrawFooterTests(SimpleTestCase):
    def test_draw_footer_centers_icon_and_domain_text(self):
        width, height = 1080, 200
        canvas = Image.new('RGB', (width, height), (50, 50, 50))
        font = result_card._load_font(result_card._FONT_REGULAR, 26)

        calls, spy = _capture_drawn_text()
        with spy:
            draw = ImageDraw.Draw(canvas)
            with patch.object(canvas, 'paste', wraps=canvas.paste) as mock_paste:
                result_card._draw_footer(
                    draw, canvas, width=width, y=100, font=font, text_color=result_card.WHITE
                )

        drawn = [content for _, content, _ in calls]
        self.assertIn('ilovevoley.es', drawn)
        self.assertTrue(mock_paste.called)
        paste_xy = mock_paste.call_args[0][1]
        text_xy = [xy for xy, content, _ in calls if content == 'ilovevoley.es'][0]
        self.assertLess(paste_xy[0], text_xy[0])
        text_w = result_card._text_width(draw, 'ilovevoley.es', font)
        total_span = (text_xy[0] + text_w) - paste_xy[0]
        expected_start = (width - total_span) // 2
        self.assertEqual(paste_xy[0], expected_start)


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
    def test_upgrades_http_urls_to_https(self, safe_get):
        safe_get.return_value = b'logo bytes'

        result_card.fetch_logo_bytes('http://intranet.rfevb.com/clubes/logos/web/cl00436.jpg')

        self.assertEqual(
            safe_get.call_args.args[0],
            'https://intranet.rfevb.com/clubes/logos/web/cl00436.jpg',
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


class TeamLogoCacheTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.team = MagicMock(display_logo_file=None, display_logo='https://fed.example/a.png')

    def test_remote_crest_is_downloaded_once(self):
        buffer = BytesIO()
        Image.new('RGBA', (40, 40), (200, 0, 0, 255)).save(buffer, format='PNG')
        fetcher = MagicMock(return_value=buffer.getvalue())

        first = result_card._team_logo_bytes(self.team, fetcher)
        second = result_card._team_logo_bytes(self.team, fetcher)

        self.assertIsNotNone(first)
        self.assertEqual(first, second)
        fetcher.assert_called_once()

    def test_download_exception_is_remembered_briefly(self):
        fetcher = MagicMock(side_effect=TimeoutError)

        self.assertIsNone(result_card._team_logo_bytes(self.team, fetcher))
        self.assertIsNone(result_card._team_logo_bytes(self.team, fetcher))

        fetcher.assert_called_once()

    def test_failed_download_is_remembered_briefly(self):
        fetcher = MagicMock(return_value=None)

        self.assertIsNone(result_card._team_logo_bytes(self.team, fetcher))
        self.assertIsNone(result_card._team_logo_bytes(self.team, fetcher))

        fetcher.assert_called_once()


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
