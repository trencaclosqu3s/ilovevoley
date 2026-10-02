from io import BytesIO
import uuid
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from PIL import Image as PILImage
from PIL.ExifTags import Base, GPS

from ilovevoley.content.models.content import image_upload_path
from ilovevoley.videos.utils import (
    convert_heic_to_jpeg,
    process_uploaded_image,
    sanitize_image,
)


def _create_image_with_gps(width=100, height=80, orientation=None, format='JPEG'):
    img = PILImage.new('RGB', (width, height), color='blue')
    exif = img.getexif()
    exif[Base.Make] = 'TestCamera'
    if orientation is not None:
        exif[Base.Orientation] = orientation
    gps_ifd = exif.get_ifd(Base.GPSInfo)
    gps_ifd[GPS.GPSLatitude] = (41.0, 23.0, 10.0)
    gps_ifd[GPS.GPSLongitude] = (2.0, 10.0, 5.0)

    buf = BytesIO()
    img.save(buf, format=format, exif=exif)
    buf.seek(0)
    return buf


class ImageSanitizationTests(SimpleTestCase):
    def test_sanitize_image_strips_exif_and_gps(self):
        raw_image = _create_image_with_gps()
        uploaded = SimpleUploadedFile('photo_with_gps.jpg', raw_image.read(), content_type='image/jpeg')

        sanitized = sanitize_image(uploaded)

        sanitized_img = PILImage.open(sanitized)
        # Pillow getexif() must be empty or contain no GPS info
        exif = sanitized_img.getexif()
        self.assertEqual(dict(exif.get_ifd(Base.GPSInfo)), {})
        self.assertNotIn(Base.Make, exif)

    def test_sanitize_image_applies_exif_orientation_transpose(self):
        # Orientation 6 means 90 degrees CW rotation.
        # Original: 120 width x 60 height.
        # Transposed upright: 60 width x 120 height.
        raw_image = _create_image_with_gps(width=120, height=60, orientation=6)
        uploaded = SimpleUploadedFile('rotated.jpg', raw_image.read(), content_type='image/jpeg')

        sanitized = sanitize_image(uploaded)

        sanitized_img = PILImage.open(sanitized)
        self.assertEqual(sanitized_img.size, (60, 120))
        # Ensure orientation tag itself is removed / not present
        self.assertNotIn(Base.Orientation, sanitized_img.getexif())

    def test_sanitize_image_resizes_large_images(self):
        # 3000 x 1500 image should be resized down to max_size=2560
        img = PILImage.new('RGB', (3000, 1500), color='green')
        buf = BytesIO()
        img.save(buf, format='JPEG')
        buf.seek(0)
        uploaded = SimpleUploadedFile('large.jpg', buf.read(), content_type='image/jpeg')

        sanitized = sanitize_image(uploaded, max_size=2560)

        sanitized_img = PILImage.open(sanitized)
        self.assertLessEqual(max(sanitized_img.size), 2560)
        self.assertEqual(sanitized_img.size, (2560, 1280))

    def test_sanitize_image_converts_rgba_to_rgb(self):
        # PNG with transparency
        img = PILImage.new('RGBA', (100, 100), color=(255, 0, 0, 128))
        buf = BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        uploaded = SimpleUploadedFile('transparent.png', buf.read(), content_type='image/png')

        sanitized = sanitize_image(uploaded)

        sanitized_img = PILImage.open(sanitized)
        self.assertEqual(sanitized_img.mode, 'RGB')
        self.assertEqual(sanitized_img.format, 'JPEG')

    def test_sanitize_image_generates_uuid_filename(self):
        raw_image = _create_image_with_gps()
        uploaded = SimpleUploadedFile('original_name_123.jpg', raw_image.read(), content_type='image/jpeg')

        sanitized = sanitize_image(uploaded)

        # Name should be <uuid4-hex>.jpg
        base_name = sanitized.name.split('.')[0]
        # Should parse as valid UUID
        parsed_uuid = uuid.UUID(base_name)
        self.assertEqual(parsed_uuid.hex, base_name)
        self.assertTrue(sanitized.name.endswith('.jpg'))

    def test_process_uploaded_image_sanitizes_jpeg_and_png(self):
        raw_image = _create_image_with_gps()
        uploaded = SimpleUploadedFile('phone_pic.jpg', raw_image.read(), content_type='image/jpeg')

        processed_file, original_ext, was_converted = process_uploaded_image(uploaded)

        self.assertEqual(original_ext, '.jpg')
        # Check that EXIF/GPS was purged
        processed_img = PILImage.open(processed_file)
        self.assertEqual(dict(processed_img.getexif().get_ifd(Base.GPSInfo)), {})
        # Name should be UUID
        base_name = processed_file.name.split('.')[0]
        self.assertEqual(uuid.UUID(base_name).hex, base_name)

    def test_image_upload_path_generates_uuid(self):
        path = image_upload_path(None, 'foto_partido_infantil.jpg')
        # Format: images/YYYY/MM/<uuid>.jpg
        parts = path.split('/')
        self.assertEqual(parts[0], 'images')
        self.assertEqual(len(parts), 4)
        filename = parts[3]
        base_name, ext = filename.split('.')
        self.assertEqual(ext, 'jpg')
        self.assertEqual(uuid.UUID(base_name).hex, base_name)

    def test_convert_heic_to_jpeg_purges_exif(self):
        raw_image = _create_image_with_gps()
        uploaded = SimpleUploadedFile('photo.heic', raw_image.read(), content_type='image/heic')
        jpeg_buf = convert_heic_to_jpeg(uploaded)
        saved_img = PILImage.open(jpeg_buf)
        self.assertEqual(dict(saved_img.getexif().get_ifd(Base.GPSInfo)), {})


from django.test import TestCase


class ModelSaveSanitizationTests(TestCase):
    def test_image_model_save_automatically_sanitizes(self):
        from ilovevoley.content.models import Image
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(username='model_save_user')
        raw_image = _create_image_with_gps()
        uploaded = SimpleUploadedFile('admin_photo.jpg', raw_image.read(), content_type='image/jpeg')

        img_obj = Image.objects.create(
            image=uploaded,
            title='Direct Model Save',
            uploaded_by=user,
        )
        img_obj.image.open()
        saved_img = PILImage.open(img_obj.image)
        self.assertEqual(dict(saved_img.getexif().get_ifd(Base.GPSInfo)), {})
        self.assertTrue(img_obj.image.name.endswith('.jpg'))
