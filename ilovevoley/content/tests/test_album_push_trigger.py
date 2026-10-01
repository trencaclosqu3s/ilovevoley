from io import BytesIO
from unittest.mock import patch
from PIL import Image as PILImage
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from ilovevoley.core.models import Organization, Season

User = get_user_model()


@override_settings(ALLOWED_HOSTS=['santjust.ilovevoley.es', 'localhost', 'testserver'])
class AlbumPushTriggerTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='CV Sant Just', slug='santjust')
        self.user = User.objects.create_superuser(username='admin', email='a@test.es', password='pwd')
        self.season = Season.objects.create(name='2025-26', start_year=2025, is_current=True)
        self.client.login(username='admin', password='pwd')

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_bulk_upload_album_triggers_push(self, mock_push):
        img = PILImage.new('RGB', (100, 100), color='blue')
        buf = BytesIO()
        img.save(buf, format='JPEG')
        buf.seek(0)
        uploaded = SimpleUploadedFile('test.jpg', buf.read(), content_type='image/jpeg')

        response = self.client.post(
            reverse('content:image_bulk_upload'),
            {
                'images': [uploaded],
                'title_0': 'Foto Album',
                'image_type': 'training',
                'season': self.season.id,
                'create_album': 'on',
                'album_name': 'Torneo de Verano',
            },
            HTTP_HOST='santjust.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 302)
        mock_push.assert_called_once()
        _, kwargs = mock_push.call_args
        self.assertEqual(kwargs.get('organization_id'), self.org.id)
        self.assertEqual(kwargs.get('title'), 'Nuevo Álbum')
        self.assertIn('Torneo de Verano', kwargs.get('body', ''))
        self.assertEqual(kwargs.get('notification_type'), 'new_album')

