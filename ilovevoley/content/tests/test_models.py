from django.core.exceptions import ValidationError
from django.test import TestCase

from ilovevoley.content.models import Video


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
