from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from ilovevoley.competitions.models import Match
from ilovevoley.content.models import Image, Video
from ilovevoley.content.views import _coerce_set_number

TINY_GIF = (
    b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
    b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00'
    b'\x00\x02\x02D\x01\x00;'
)


class VideoSetNumberAndYoutubeIdTest(TestCase):
    def test_set_number_accepts_null(self):
        video = Video(title='Sin set', youtube_url='https://youtu.be/abc123', set_number=None)
        video.full_clean(exclude=['created_by'])  # no debe lanzar por set_number
        self.assertIsNone(video.set_number)

    def test_set_number_rejects_zero(self):
        video = Video(title='Set 0', youtube_url='https://youtu.be/abc123', set_number=0)
        with self.assertRaises(ValidationError):
            video.full_clean(exclude=['created_by'])

    def test_get_video_id_parses_watch_and_short_urls(self):
        self.assertEqual(
            Video(youtube_url='https://www.youtube.com/watch?v=XYZ789').get_video_id(),
            'XYZ789',
        )
        self.assertEqual(
            Video(youtube_url='https://youtu.be/XYZ789?t=3').get_video_id(),
            'XYZ789',
        )

    def test_get_thumbnail_url_uses_video_id(self):
        video = Video(youtube_url='https://www.youtube.com/watch?v=XYZ789')
        self.assertEqual(
            video.get_thumbnail_url(),
            'https://i.ytimg.com/vi/XYZ789/hqdefault.jpg',
        )

    def test_get_thumbnail_url_returns_none_for_unknown_url(self):
        self.assertIsNone(Video(youtube_url='https://example.com/x').get_thumbnail_url())


class SetNumberRequiresMatchTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='u', password='p')
        self.match = Match.objects.create(match_date=timezone.now())

    def test_video_set_number_nulled_without_match(self):
        video = Video.objects.create(
            title='Sin partido',
            youtube_url='https://youtu.be/abc',
            set_number=2,
            created_by=self.user,
        )
        video.refresh_from_db()
        self.assertIsNone(video.set_number)

    def test_video_set_number_persists_with_match(self):
        video = Video.objects.create(
            title='Con partido',
            youtube_url='https://youtu.be/abc',
            match=self.match,
            set_number=2,
            created_by=self.user,
        )
        video.refresh_from_db()
        self.assertEqual(video.set_number, 2)

    def test_image_set_number_nulled_without_match(self):
        image = Image.objects.create(
            image=SimpleUploadedFile('x.jpg', TINY_GIF, content_type='image/jpeg'),
            title='Sin partido',
            set_number=3,
            uploaded_by=self.user,
        )
        image.refresh_from_db()
        self.assertIsNone(image.set_number)

    def test_image_set_number_persists_with_match(self):
        image = Image.objects.create(
            image=SimpleUploadedFile('x.jpg', TINY_GIF, content_type='image/jpeg'),
            title='Con partido',
            match=self.match,
            set_number=3,
            uploaded_by=self.user,
        )
        image.refresh_from_db()
        self.assertEqual(image.set_number, 3)


class CoerceSetNumberTest(TestCase):
    def test_invalid_values_become_none(self):
        for raw in (None, '', 'abc', '0', '-1'):
            self.assertIsNone(_coerce_set_number(raw), raw)

    def test_valid_values_become_int(self):
        self.assertEqual(_coerce_set_number('1'), 1)
        self.assertEqual(_coerce_set_number('5'), 5)
