import base64
from io import BytesIO

from django.test import SimpleTestCase
from PIL import Image, ImageDraw

from ilovevoley.core.image_utils import InvalidImageError, decode_cropped_image, normalize_crest


def _data_uri(image_format, mime_type, size=(10, 10)):
    buffer = BytesIO()
    Image.new('RGB', size, (200, 0, 0)).save(buffer, format=image_format)
    encoded = base64.b64encode(buffer.getvalue()).decode()
    return f'data:{mime_type};base64,{encoded}'


class DecodeCroppedImageTests(SimpleTestCase):
    def test_valid_png_is_reencoded_to_jpeg(self):
        content = decode_cropped_image(_data_uri('PNG', 'image/png'))

        self.assertTrue(content.name.endswith('.jpg'))
        with Image.open(content) as image:
            self.assertEqual(image.format, 'JPEG')

    def test_valid_webp_is_accepted(self):
        content = decode_cropped_image(_data_uri('WEBP', 'image/webp'))

        self.assertTrue(content.name.endswith('.jpg'))

    def test_html_mime_type_is_rejected(self):
        payload = base64.b64encode(b'<script>alert(document.domain)</script>').decode()

        with self.assertRaises(InvalidImageError):
            decode_cropped_image(f'data:image/html;base64,{payload}')

    def test_script_declared_as_jpeg_is_rejected(self):
        payload = base64.b64encode(b'<script>alert(1)</script>').decode()

        with self.assertRaises(InvalidImageError):
            decode_cropped_image(f'data:image/jpeg;base64,{payload}')

    def test_disallowed_mime_type_is_rejected(self):
        with self.assertRaises(InvalidImageError):
            decode_cropped_image(_data_uri('GIF', 'image/gif'))

    def test_content_mismatching_header_is_rejected(self):
        with self.assertRaises(InvalidImageError):
            decode_cropped_image(_data_uri('PNG', 'image/jpeg'))

    def test_oversized_payload_is_rejected(self):
        with self.assertRaises(InvalidImageError):
            decode_cropped_image(_data_uri('PNG', 'image/png'), max_size=10)

    def test_non_data_uri_is_rejected(self):
        with self.assertRaises(InvalidImageError):
            decode_cropped_image('https://example.com/photo.jpg')


class ImageToDataUriTests(SimpleTestCase):
    def test_converts_content_file_to_data_uri(self):
        from django.core.files.base import ContentFile
        from ilovevoley.core.image_utils import image_to_data_uri

        cf = ContentFile(b'\xff\xd8\xff\xe0\x00\x10JFIF', name='test.jpg')
        uri = image_to_data_uri(cf)
        self.assertIsNotNone(uri)
        self.assertTrue(uri.startswith('data:image/jpeg;base64,'))

    def test_returns_none_on_none_or_missing_file(self):
        from ilovevoley.core.image_utils import image_to_data_uri

        self.assertIsNone(image_to_data_uri(None))



class NormalizeCrestTests(SimpleTestCase):
    """Los escudos de la federación son JPEG con fondo blanco y proporciones dispares."""

    @staticmethod
    def _federation_crest():
        image = Image.new('RGB', (300, 200), (255, 255, 255))
        draw = ImageDraw.Draw(image)
        draw.rectangle([100, 40, 200, 160], fill=(20, 40, 120))
        draw.rectangle([140, 80, 160, 120], fill=(255, 255, 255))  # blanco interior
        buffer = BytesIO()
        image.save(buffer, format='JPEG', quality=95)
        return buffer.getvalue()

    def test_crops_to_centered_square_with_transparent_background(self):
        result = Image.open(BytesIO(normalize_crest(self._federation_crest())))

        self.assertEqual(result.width, result.height)
        self.assertEqual(result.getpixel((0, 0))[3], 0)
        centre = (result.width // 2, result.height // 2)
        self.assertEqual(result.getpixel(centre)[3], 255)  # el blanco interior se conserva
        left, _, right, _ = result.getchannel('A').getbbox()
        self.assertGreater(left, result.width * 0.1)
        self.assertLess(right, result.width * 0.9)

    def test_returns_none_for_non_images_and_blank_images(self):
        blank = BytesIO()
        Image.new('RGB', (50, 50), (255, 255, 255)).save(blank, format='PNG')

        self.assertIsNone(normalize_crest(b'<html>no soy una imagen</html>'))
        self.assertIsNone(normalize_crest(blank.getvalue()))
