import base64
from io import BytesIO

from django.test import SimpleTestCase
from PIL import Image

from ilovevoley.core.image_utils import InvalidImageError, decode_cropped_image


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
