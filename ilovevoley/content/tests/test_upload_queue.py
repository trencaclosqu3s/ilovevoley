"""Tests de la cola de subida de fotos tolerante a mala cobertura (#611).

Justificación (docs/ai-guidelines/testing-guidelines.md):
- Protege la idempotencia ante reintentos de red (evita fotos y notificaciones duplicadas).
- Verifica el aislamiento multi-tenant en álbumes y partidos enviados al endpoint API.
- Comprueba la consolidación por lote (batch_id) de correos de moderación y push de álbum.
- Comprueba el rechazo con 400 de archivos corruptos o >10 MB en el camino crítico de subida.
"""
import shutil
import tempfile
import uuid
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image as PILImage

from ilovevoley.competitions.models import League, Match
from ilovevoley.content.models import Image
from ilovevoley.content.services import queue_upload_batch_notifications
from ilovevoley.content.tasks import flush_upload_batch_notifications_task
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.teams.models import Club, Team
from ilovevoley.users.models import Membership

User = get_user_model()


def make_jpeg_upload(name='IMG_0001.jpg', size=(80, 60), color='navy'):
    buf = BytesIO()
    PILImage.new('RGB', size, color=color).save(buf, format='JPEG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/jpeg')


@override_settings(
    ALLOWED_HOSTS=['santjosep.ilovevoley.es', 'soller.ilovevoley.es', 'localhost', 'testserver'],
    UPLOAD_BATCH_DEBOUNCE_SECONDS=15,
)
class UploadBatchNotificationConsolidationTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.addCleanup(self.override.disable)
        cache.clear()

        self.org, _ = Organization.objects.get_or_create(
            slug='santjosep', defaults={'name': 'CV Sant Josep', 'is_active': True}
        )
        self.user = User.objects.create_user(username='uploader', password='pwd')
        Membership.objects.create(user=self.user, organization=self.org, is_approved=True)
        self.season = Season.objects.create(name='2026-27', start_year=2026, end_year=2027, is_current=True)
        self.cat = Category.objects.create(name='Cadete', is_active=True)

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    @patch('ilovevoley.core.tasks.notify_images_pending_batch_task.delay')
    @patch('ilovevoley.content.tasks.flush_upload_batch_notifications_task.apply_async')
    def test_batch_consolidates_pending_emails_and_single_album_push(
        self, mock_apply_async, mock_pending_email, mock_push
    ):
        batch_id = str(uuid.uuid4())
        album_id = str(uuid.uuid4())

        img1 = Image.objects.create(
            image=make_jpeg_upload('1.jpg'),
            title='Foto 1',
            uploaded_by=self.user,
            organization=self.org,
            season=self.season,
            status='pending',
            album_group_id=album_id,
            album_name='Torneo Navidad',
        )
        img2 = Image.objects.create(
            image=make_jpeg_upload('2.jpg'),
            title='Foto 2',
            uploaded_by=self.user,
            organization=self.org,
            season=self.season,
            status='pending',
            album_group_id=album_id,
            album_name='Torneo Navidad',
        )

        with self.captureOnCommitCallbacks(execute=True):
            queue_upload_batch_notifications(
                organization_id=self.org.id,
                batch_id=batch_id,
                image_id=img1.id,
                is_pending=True,
                is_new_album=True,
                album_group_id=album_id,
                album_name='Torneo Navidad',
                category_ids=[self.cat.id],
            )
            queue_upload_batch_notifications(
                organization_id=self.org.id,
                batch_id=batch_id,
                image_id=img2.id,
                is_pending=True,
                is_new_album=True,
                album_group_id=album_id,
                album_name='Torneo Navidad',
                category_ids=[self.cat.id],
            )

        self.assertEqual(mock_apply_async.call_count, 1)

        result = flush_upload_batch_notifications_task(self.org.id, batch_id)
        self.assertEqual(result['pending_notified'], 2)
        self.assertTrue(result['album_push_sent'])
        mock_pending_email.assert_called_once_with([img1.id, img2.id])
        mock_push.assert_called_once()
        self.assertEqual(mock_push.call_args.kwargs['notification_type'], 'new_album')
        self.assertEqual(mock_push.call_args.kwargs['category_ids'], [self.cat.id])

        img3 = Image.objects.create(
            image=make_jpeg_upload('3.jpg'),
            title='Foto 3',
            uploaded_by=self.user,
            organization=self.org,
            season=self.season,
            status='pending',
            album_group_id=album_id,
            album_name='Torneo Navidad',
        )
        with self.captureOnCommitCallbacks(execute=True):
            queue_upload_batch_notifications(
                organization_id=self.org.id,
                batch_id=batch_id,
                image_id=img3.id,
                is_pending=True,
                is_new_album=True,
                album_group_id=album_id,
                album_name='Torneo Navidad',
                category_ids=[self.cat.id],
            )
        result_late = flush_upload_batch_notifications_task(self.org.id, batch_id)
        self.assertEqual(result_late['pending_notified'], 1)
        self.assertFalse(result_late['album_push_sent'])
        self.assertEqual(mock_push.call_count, 1)


@override_settings(
    ALLOWED_HOSTS=['santjosep.ilovevoley.es', 'soller.ilovevoley.es', 'localhost', 'testserver'],
)
class ImageQueueUploadApiTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.addCleanup(self.override.disable)
        cache.clear()

        self.club_sj = Club.objects.create(official_name='CV Sant Josep', federation_id='SJ1')
        self.org, _ = Organization.objects.get_or_create(
            slug='santjosep', defaults={'name': 'CV Sant Josep', 'is_active': True}
        )
        self.org.club = self.club_sj
        self.org.save()

        self.club_soller = Club.objects.create(official_name='CV Soller', federation_id='SO1')
        self.other_org = Organization.objects.create(
            slug='soller', name='CV Soller', club=self.club_soller, is_active=True
        )

        self.user = User.objects.create_user(username='member_sj', password='pwd')
        Membership.objects.create(user=self.user, organization=self.org, is_approved=True)
        self.season = Season.objects.create(name='2026-27', start_year=2026, end_year=2027, is_current=True)
        self.cat = Category.objects.create(name='Senior', is_active=True)

        self.url = reverse('content:image_queue_upload_api')
        self.client.force_login(self.user)

    def test_idempotent_retry_with_same_client_upload_id_creates_single_image(self):
        """Review Focus 1: si la respuesta se pierde y el cliente reintenta con el mismo
        client_upload_id, se devuelve la misma Image sin duplicar filas ni avisos."""
        client_upload_id = str(uuid.uuid4())
        batch_id = str(uuid.uuid4())

        with patch('ilovevoley.content.views.queue_upload_batch_notifications') as mock_batch:
            r1 = self.client.post(
                self.url,
                {
                    'client_upload_id': client_upload_id,
                    'batch_id': batch_id,
                    'image': make_jpeg_upload('IMG_1234.jpg'),
                    'image_type': 'training',
                    'shared_title': 'Entreno Viernes',
                },
                HTTP_HOST='santjosep.ilovevoley.es',
            )
            self.assertEqual(r1.status_code, 200)
            data1 = r1.json()
            self.assertTrue(data1['ok'])
            self.assertFalse(data1['deduplicated'])

            r2 = self.client.post(
                self.url,
                {
                    'client_upload_id': client_upload_id,
                    'batch_id': batch_id,
                    'image': make_jpeg_upload('IMG_1234.jpg'),
                    'image_type': 'training',
                    'shared_title': 'Entreno Viernes',
                },
                HTTP_HOST='santjosep.ilovevoley.es',
            )
            self.assertEqual(r2.status_code, 200)
            data2 = r2.json()
            self.assertTrue(data2['ok'])
            self.assertTrue(data2['deduplicated'])
            self.assertEqual(data1['image_id'], data2['image_id'])
            self.assertEqual(Image.objects.count(), 1)
            self.assertEqual(mock_batch.call_count, 1)

    def test_album_group_id_groups_batch_and_blocks_cross_tenant_album(self):
        """Review Focus 2: el cliente puede agrupar un lote en un album_group_id nuevo,
        pero no puede inyectar fotos en un album_group_id perteneciente a otro tenant."""
        album_id = str(uuid.uuid4())
        batch_id = str(uuid.uuid4())

        for idx in range(2):
            resp = self.client.post(
                self.url,
                {
                    'client_upload_id': str(uuid.uuid4()),
                    'batch_id': batch_id,
                    'image': make_jpeg_upload(f'IMG_000{idx}.jpg'),
                    'image_type': 'celebration',
                    'create_album': 'true',
                    'album_group_id': album_id,
                    'album_name': 'Cena de Club',
                    'categories': [str(self.cat.id)],
                },
                HTTP_HOST='santjosep.ilovevoley.es',
            )
            self.assertEqual(resp.status_code, 200)

        images = list(Image.objects.filter(organization=self.org).order_by('id'))
        self.assertEqual(len(images), 2)
        self.assertEqual(str(images[0].album_group_id), album_id)
        self.assertEqual(images[0].album_name, 'Cena de Club')
        self.assertEqual(images[0].title, 'Cena de Club - 001')
        self.assertEqual(images[1].title, 'Cena de Club - 002')

        other_album_id = uuid.uuid4()
        Image.objects.create(
            image=make_jpeg_upload('other.jpg'),
            title='Foto Soller',
            uploaded_by=self.user,
            organization=self.other_org,
            season=self.season,
            album_group_id=other_album_id,
            album_name='Album Soller',
        )
        cross_resp = self.client.post(
            self.url,
            {
                'client_upload_id': str(uuid.uuid4()),
                'batch_id': str(uuid.uuid4()),
                'image': make_jpeg_upload('hack.jpg'),
                'image_type': 'other',
                'album_group_id': str(other_album_id),
                'album_name': 'Intruso',
            },
            HTTP_HOST='santjosep.ilovevoley.es',
        )
        self.assertEqual(cross_resp.status_code, 400)
        self.assertFalse(cross_resp.json()['ok'])

    def test_rejects_match_belonging_to_another_club(self):
        """Review Focus 3: un partido cuyos equipos no son del club del tenant devuelve 400."""
        league = League.objects.create(name='Liga Balear', federation_id='L-B1', season=self.season)
        team_a = Team.objects.create(
            name='CV Soller A', federation_id='T-SO1', club=self.club_soller, category=self.cat
        )
        team_b = Team.objects.create(
            name='CV Manacor A', federation_id='T-MA1', club=self.club_soller, category=self.cat
        )
        foreign_match = Match.objects.create(
            league=league,
            home_team=team_a,
            away_team=team_b,
            match_date=timezone.now(),
            federation_id='M-FOREIGN-1',
        )
        resp = self.client.post(
            self.url,
            {
                'client_upload_id': str(uuid.uuid4()),
                'batch_id': str(uuid.uuid4()),
                'image': make_jpeg_upload('match.jpg'),
                'image_type': 'match',
                'match': str(foreign_match.id),
            },
            HTTP_HOST='santjosep.ilovevoley.es',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Image.objects.count(), 0)

    def test_rejects_invalid_or_oversized_file_with_400_json(self):
        """Review Focus 4: archivo corrupto o >10 MB devuelve 400 JSON."""
        bad_file = SimpleUploadedFile('fake.jpg', b'not an image', content_type='image/jpeg')
        resp_bad = self.client.post(
            self.url,
            {
                'client_upload_id': str(uuid.uuid4()),
                'image': bad_file,
                'image_type': 'other',
            },
            HTTP_HOST='santjosep.ilovevoley.es',
        )
        self.assertEqual(resp_bad.status_code, 400)
        self.assertFalse(resp_bad.json()['ok'])

        huge_file = SimpleUploadedFile(
            'huge.jpg', b'x' * (10 * 1024 * 1024 + 10), content_type='image/jpeg'
        )
        resp_huge = self.client.post(
            self.url,
            {
                'client_upload_id': str(uuid.uuid4()),
                'image': huge_file,
                'image_type': 'other',
            },
            HTTP_HOST='santjosep.ilovevoley.es',
        )
        self.assertEqual(resp_huge.status_code, 400)
        self.assertIn('10MB', resp_huge.json()['error'])


class UploadQueueFrontendIntegrationTests(TestCase):
    def setUp(self):
        self.org, _ = Organization.objects.get_or_create(
            slug='santjosep', defaults={'name': 'CV Sant Josep', 'is_active': True}
        )
        self.user = User.objects.create_user(username='front_user', password='pwd')
        Membership.objects.create(user=self.user, organization=self.org, is_approved=True)
        Season.objects.create(name='2026-27', start_year=2026, end_year=2027, is_current=True)

    @override_settings(ALLOWED_HOSTS=['santjosep.ilovevoley.es', 'localhost', 'testserver'])
    def test_upload_pages_include_queue_widget_and_api_endpoint(self):
        """Verifica que las vistas de subida cargan el widget flotante y el endpoint de la cola."""
        self.client.force_login(self.user)
        resp_single = self.client.get(
            reverse('content:image_upload'), HTTP_HOST='santjosep.ilovevoley.es'
        )
        self.assertEqual(resp_single.status_code, 200)
        self.assertContains(resp_single, 'id="upload-queue-widget"')
        self.assertContains(resp_single, reverse('content:image_queue_upload_api'))
        self.assertContains(resp_single, 'upload_queue')

        resp_bulk = self.client.get(
            reverse('content:image_bulk_upload'), HTTP_HOST='santjosep.ilovevoley.es'
        )
        self.assertEqual(resp_bulk.status_code, 200)
        self.assertContains(resp_bulk, 'id="upload-queue-widget"')

    def test_service_worker_exposes_background_sync_for_photo_uploads(self):
        """El Service Worker debe escuchar el evento sync con el tag 'sync-photo-uploads'."""
        resp = self.client.get('/sw.js')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'sync-photo-uploads')
        self.assertContains(resp, "addEventListener('sync'")
