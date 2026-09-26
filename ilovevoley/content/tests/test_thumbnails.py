import shutil
import tempfile
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string
from django.test import TestCase, override_settings

from ilovevoley.content.models import Image
from ilovevoley.content.thumbnails import generate_image_thumbnails


def _jpeg_bytes(width, height):
    from PIL import Image as PILImage

    buffer = BytesIO()
    PILImage.new('RGB', (width, height), (120, 30, 200)).save(buffer, format='JPEG')
    return buffer.getvalue()


def _avif_supported():
    from PIL import features

    return features.check('avif')


class ThumbnailGenerationTests(TestCase):
    """La generación de miniaturas y sus URLs srcset deben ser correctas."""

    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.user = get_user_model().objects.create_user(username='tester', password='x')

    def _create_image(self, width=1200, height=800, filename='foto.jpg'):
        return Image.objects.create(
            image=SimpleUploadedFile(filename, _jpeg_bytes(width, height), content_type='image/jpeg'),
            title='Foto de prueba',
            uploaded_by=self.user,
            status='approved',
        )

    def test_genera_variantes_y_las_persiste(self):
        image = self._create_image()

        generated = generate_image_thumbnails(image)

        self.assertIn('thumbnail_small', generated)
        self.assertIn('thumbnail_large', generated)
        stored = Image.objects.get(pk=image.pk)
        self.assertTrue(stored.thumbnail_small.name.endswith('_400.webp'))
        self.assertTrue(stored.thumbnail_large.name.endswith('_1600.webp'))
        self.assertTrue(stored.thumbnail_small.storage.exists(stored.thumbnail_small.name))
        self.assertTrue(stored.thumbnail_large.storage.exists(stored.thumbnail_large.name))

    def test_miniatura_pequena_no_supera_400px(self):
        image = self._create_image(width=1200, height=800)

        generate_image_thumbnails(image)
        stored = Image.objects.get(pk=image.pk)

        self.assertEqual(stored.thumbnail_small.width, 400)
        self.assertLess(stored.thumbnail_small.height, 400)

    def test_no_agranda_imagenes_menores_que_el_objetivo(self):
        image = self._create_image(width=200, height=150)

        generate_image_thumbnails(image)
        stored = Image.objects.get(pk=image.pk)

        self.assertEqual(stored.thumbnail_small.width, 200)

    def test_genera_avif_si_la_build_lo_soporta(self):
        image = self._create_image()

        generated = generate_image_thumbnails(image)

        if _avif_supported():
            self.assertIn('thumbnail_small_avif', generated)
            self.assertIn('thumbnail_large_avif', generated)
        else:
            self.assertNotIn('thumbnail_small_avif', generated)

    def test_thumbnail_url_usa_variante_y_cae_al_original(self):
        sin_variantes = self._create_image(filename='original.jpg')
        self.assertEqual(sin_variantes.thumbnail_url, sin_variantes.image.url)
        self.assertEqual(sin_variantes.thumbnail_srcset, '')

        generate_image_thumbnails(sin_variantes)
        con_variantes = Image.objects.get(pk=sin_variantes.pk)
        self.assertIn('_400.webp', con_variantes.thumbnail_url)
        self.assertIn('400w', con_variantes.thumbnail_srcset)
        self.assertIn('1600w', con_variantes.thumbnail_srcset)

    def test_include_renderiza_picture_con_srcset(self):
        image = self._create_image()
        generate_image_thumbnails(image)
        image.refresh_from_db()

        html = render_to_string('content/_thumbnail.html', {'image': image, 'sizes': '100vw'})

        self.assertIn('srcset=', html)
        self.assertIn('image/webp', html)
        self.assertIn('400w', html)
