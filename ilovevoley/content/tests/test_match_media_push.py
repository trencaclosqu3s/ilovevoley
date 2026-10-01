from io import BytesIO
from unittest.mock import patch
from PIL import Image as PILImage

from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ilovevoley.competitions.models import League, Match
from ilovevoley.content.models import Image
from ilovevoley.content.services import moderate_image
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.teams.models import Club, Team
from ilovevoley.users.models import Membership

User = get_user_model()


def _create_test_image_file(name='test.jpg'):
    img = PILImage.new('RGB', (100, 100), color='blue')
    buf = BytesIO()
    img.save(buf, format='JPEG')
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type='image/jpeg')


@override_settings(ALLOWED_HOSTS=['santjust.ilovevoley.es', 'localhost', 'testserver'])
class MatchMediaPushTest(TestCase):
    def setUp(self):
        cache.clear()
        self.club = Club.objects.create(official_name='Sant Just', federation_id='SJ01')
        self.org = Organization.objects.create(name='CV Sant Just', slug='santjust', club=self.club)
        self.user = User.objects.create_superuser(username='admin', email='a@test.es', password='pwd')
        self.season = Season.objects.create(name='2025-26', start_year=2025, is_current=True)
        self.category = Category.objects.create(name='Senior Femenino')
        self.team1 = Team.objects.create(
            name='Senior A', club=self.club, federation_id='T01', category=self.category
        )
        self.team2 = Team.objects.create(name='Rival B', federation_id='T02')
        self.league = League.objects.create(name='1a Balear', season=self.season)
        self.league.categories.add(self.category)
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team1,
            away_team=self.team2,
            match_date=timezone.now(),
        )
        self.client = Client()
        self.client.login(username='admin', password='pwd')

    def tearDown(self):
        cache.clear()

    @patch('ilovevoley.content.tasks.notify_match_media_push_task.apply_async')
    def test_queue_match_media_push_debounces_tasks(self, mock_apply_async):
        from ilovevoley.content.services import queue_match_media_push

        with self.captureOnCommitCallbacks(execute=True):
            first = queue_match_media_push(self.match.id, 'photo', self.org.id)
            second = queue_match_media_push(self.match.id, 'photo', self.org.id)
            third = queue_match_media_push(self.match.id, 'video', self.org.id)

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertFalse(third)

        # Solo una tarea Celery programada con countdown
        mock_apply_async.assert_called_once()
        _, kwargs = mock_apply_async.call_args
        self.assertEqual(kwargs.get('countdown'), settings.MATCH_MEDIA_PUSH_DEBOUNCE_SECONDS)

        # Los medios pendientes en caché acumulan tanto fotos como vídeos
        pending = cache.get(f"match_media_push_pending:{self.org.id}:{self.match.id}")
        self.assertIsNotNone(pending)
        self.assertTrue(pending.get('photos'))
        self.assertTrue(pending.get('videos'))

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_notify_match_media_push_task_photos_only(self, mock_push):
        from ilovevoley.content.tasks import notify_match_media_push_task

        cache.set(
            f"match_media_push_pending:{self.org.id}:{self.match.id}",
            {'photos': True, 'videos': False},
            timeout=120,
        )

        res = notify_match_media_push_task(self.org.id, self.match.id)
        self.assertTrue(res)

        mock_push.assert_called_once()
        _, kwargs = mock_push.call_args
        self.assertEqual(kwargs['organization_id'], self.org.id)
        self.assertIn('Fotos: Senior A vs Rival B', kwargs['title'])
        self.assertIn('Se han subido fotos del partido Senior A - Rival B', kwargs['body'])
        self.assertEqual(kwargs['notification_type'], 'match_media')
        self.assertIn(self.category.id, kwargs['category_ids'])
        self.assertEqual(kwargs['url'], reverse('competitions:match_detail', args=[self.match.id]))

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_notify_match_media_push_task_videos_only(self, mock_push):
        from ilovevoley.content.tasks import notify_match_media_push_task

        cache.set(
            f"match_media_push_pending:{self.org.id}:{self.match.id}",
            {'photos': False, 'videos': True},
            timeout=120,
        )

        res = notify_match_media_push_task(self.org.id, self.match.id)
        self.assertTrue(res)

        mock_push.assert_called_once()
        _, kwargs = mock_push.call_args
        self.assertEqual(kwargs['organization_id'], self.org.id)
        self.assertIn('Vídeos: Senior A vs Rival B', kwargs['title'])
        self.assertIn('Se han subido vídeos del partido Senior A - Rival B', kwargs['body'])
        self.assertEqual(kwargs['notification_type'], 'match_media')

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_notify_match_media_push_task_both_photos_and_videos(self, mock_push):
        from ilovevoley.content.tasks import notify_match_media_push_task

        cache.set(
            f"match_media_push_pending:{self.org.id}:{self.match.id}",
            {'photos': True, 'videos': True},
            timeout=120,
        )

        res = notify_match_media_push_task(self.org.id, self.match.id)
        self.assertTrue(res)

        mock_push.assert_called_once()
        _, kwargs = mock_push.call_args
        self.assertEqual(kwargs['organization_id'], self.org.id)
        self.assertIn('Fotos y vídeos: Senior A vs Rival B', kwargs['title'])
        self.assertIn('Se han subido fotos y vídeos del partido Senior A - Rival B', kwargs['body'])
        self.assertEqual(kwargs['notification_type'], 'match_media')

    @patch('ilovevoley.content.views.queue_match_media_push')
    def test_image_bulk_upload_with_match_queues_match_media_push(self, mock_queue):
        uploaded = _create_test_image_file()
        response = self.client.post(
            reverse('content:image_bulk_upload'),
            {
                'images': [uploaded],
                'title_0': 'Foto Partido',
                'image_type': 'match',
                'season': self.season.id,
                'match': self.match.id,
            },
            HTTP_HOST='santjust.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 302)
        mock_queue.assert_called_once_with(
            match_id=self.match.id,
            media_type='photo',
            organization_id=self.org.id,
        )

    @patch('ilovevoley.content.views.queue_match_media_push')
    def test_image_upload_with_match_queues_match_media_push(self, mock_queue):
        uploaded = _create_test_image_file()
        response = self.client.post(
            reverse('content:image_upload'),
            {
                'image': uploaded,
                'title': 'Foto Individual Partido',
                'image_type': 'match',
                'season': self.season.id,
                'match': self.match.id,
            },
            HTTP_HOST='santjust.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 302)
        mock_queue.assert_called_once_with(
            match_id=self.match.id,
            media_type='photo',
            organization_id=self.org.id,
        )

    @patch('ilovevoley.content.views.queue_match_media_push')
    def test_pending_image_upload_does_not_queue_match_media_push(self, mock_queue):
        """Una foto aún pendiente de moderación no debe avisar: no es visible (#286)."""
        member = User.objects.create_user(username='member', password='pwd')
        Membership.objects.create(
            user=member, organization=self.org, role='manager', is_approved=True
        )
        self.client.login(username='member', password='pwd')

        response = self.client.post(
            reverse('content:image_upload'),
            {
                'image': _create_test_image_file('pending.jpg'),
                'title': 'Foto pendiente',
                'image_type': 'match',
                'season': self.season.id,
                'match': self.match.id,
            },
            HTTP_HOST='santjust.ilovevoley.es',
        )

        self.assertEqual(response.status_code, 302)
        mock_queue.assert_not_called()

    @patch('ilovevoley.content.views.queue_match_media_push')
    def test_video_create_with_match_queues_match_media_push(self, mock_queue):
        response = self.client.post(
            reverse('content:video_create'),
            {
                'title': 'Vídeo Partido',
                'youtube_url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
                'match': self.match.id,
                'category': self.category.id,
            },
            HTTP_HOST='santjust.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 302)
        mock_queue.assert_called_once_with(
            match_id=self.match.id,
            media_type='video',
            organization_id=self.org.id,
        )

    @patch('ilovevoley.content.views.queue_match_media_push')
    def test_video_bulk_create_with_match_queues_match_media_push(self, mock_queue):
        response = self.client.post(
            reverse('content:video_bulk_create'),
            {
                'match': self.match.id,
                'category': self.category.id,
                'videos-TOTAL_FORMS': '1',
                'videos-INITIAL_FORMS': '0',
                'videos-MIN_NUM_FORMS': '0',
                'videos-MAX_NUM_FORMS': '10',
                'videos-0-title': 'Set 1 Partido',
                'videos-0-youtube_url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
                'videos-0-set_number': '1',
            },
            HTTP_HOST='santjust.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 302)
        mock_queue.assert_called_once_with(
            match_id=self.match.id,
            media_type='video',
            organization_id=self.org.id,
        )

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_multiple_rapid_uploads_same_match_send_single_push(self, mock_push):
        """N subidas del mismo partido en la ventana envían un solo push consolidado."""
        # Primera subida: fotos via bulk
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse('content:image_bulk_upload'),
                {
                    'images': [_create_test_image_file('img1.jpg')],
                    'title_0': 'Foto Lote 1',
                    'image_type': 'match',
                    'season': self.season.id,
                    'match': self.match.id,
                },
                HTTP_HOST='santjust.ilovevoley.es',
            )

        # Segunda subida: foto individual
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse('content:image_upload'),
                {
                    'image': _create_test_image_file('img2.jpg'),
                    'title': 'Foto Individual 2',
                    'image_type': 'match',
                    'season': self.season.id,
                    'match': self.match.id,
                },
                HTTP_HOST='santjust.ilovevoley.es',
            )

        # Tercera subida: vídeo del partido
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse('content:video_create'),
                {
                    'title': 'Vídeo Partido',
                    'youtube_url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
                    'match': self.match.id,
                    'category': self.category.id,
                },
                HTTP_HOST='santjust.ilovevoley.es',
            )

        # Se envió un único push para la ráfaga
        self.assertEqual(mock_push.call_count, 1)
        _, kwargs = mock_push.call_args
        self.assertEqual(kwargs['organization_id'], self.org.id)
        self.assertEqual(kwargs['notification_type'], 'match_media')
        self.assertIn('Fotos', kwargs['title'])


class ModerationApprovalTriggersMediaPushTest(TestCase):
    """El aviso de fotos de partido se encola al aprobar la imagen, no al subirla (#286)."""

    def setUp(self):
        cache.clear()
        self.club = Club.objects.create(official_name='Sant Just', federation_id='SJ02')
        self.org = Organization.objects.create(name='CV Sant Just', slug='santjust2', club=self.club)
        self.season = Season.objects.create(name='2024-25', start_year=2024, is_current=True)
        self.manager = User.objects.create_user(username='manager', password='pwd')
        Membership.objects.create(
            user=self.manager, organization=self.org, role='manager', is_approved=True
        )
        self.league = League.objects.create(name='1a Balear', season=self.season)
        self.home = Team.objects.create(name='Senior A', club=self.club, federation_id='T11')
        self.away = Team.objects.create(name='Rival B', federation_id='T12')
        self.match = Match.objects.create(
            league=self.league, home_team=self.home, away_team=self.away, match_date=timezone.now()
        )
        self.image = Image.objects.create(
            image=_create_test_image_file(),
            title='Foto pendiente',
            uploaded_by=self.manager,
            organization=self.org,
            match=self.match,
            status='pending',
        )

    def tearDown(self):
        cache.clear()

    @patch('ilovevoley.content.services.queue_match_media_push')
    def test_approving_image_queues_match_media_push(self, mock_queue):
        moderate_image(actor=self.manager, tenant=self.org, image=self.image, decision='approve')

        mock_queue.assert_called_once_with(
            match_id=self.match.id,
            media_type='photo',
            organization_id=self.org.id,
        )

    @patch('ilovevoley.content.services.queue_match_media_push')
    def test_rejecting_image_does_not_queue_match_media_push(self, mock_queue):
        moderate_image(actor=self.manager, tenant=self.org, image=self.image, decision='reject')

        mock_queue.assert_not_called()

    @override_settings(GOOGLE_VISION_ENABLED=True, AUTO_MODERATION_ENABLED=True)
    @patch('ilovevoley.content.services.queue_match_media_push')
    @patch('ilovevoley.content.tasks.check_image_with_vision_api')
    def test_vision_auto_approval_queues_match_media_push(self, mock_vision, mock_queue):
        """La auto-aprobación por Vision también avisa, ya que entonces la foto es visible."""
        from ilovevoley.content.tasks import analyze_image_with_vision_task

        mock_vision.return_value = {
            'safe': True,
            'labels': ['volleyball'],
            'text': '',
            'details': {'api_response_ok': True},
        }

        analyze_image_with_vision_task(self.image.id, notify_if_pending=False)

        self.image.refresh_from_db()
        self.assertEqual(self.image.status, 'approved')
        mock_queue.assert_called_once_with(
            match_id=self.match.id,
            media_type='photo',
            organization_id=self.org.id,
        )
