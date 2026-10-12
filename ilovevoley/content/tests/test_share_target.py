"""Tests del share target PWA (#524).

Justificación (docs/ai-guidelines/testing-guidelines.md): flujo nuevo con efectos
persistentes (filas SharedUpload + archivos en MEDIA), gate de autenticación y
validación de tipos/tamaños contra una entrada (POST sin CSRF desde el SO) que
solo puede romperse en producción.
"""
import shutil
import tempfile
from datetime import timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image as PILImage

from ilovevoley.content.models import SharedUpload
from ilovevoley.core.models import Organization, Season
from ilovevoley.users.models import Membership


def jpeg_bytes(name='IMG_0001.jpg'):
    buf = BytesIO()
    PILImage.new('RGB', (40, 40), color='red').save(buf, format='JPEG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/jpeg')


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'ilovevoley.es', 'localhost', 'testserver'])
class ShareTargetReceiverTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.addCleanup(self.override.disable)
        cache.clear()

        self.org = Organization.objects.create(slug='testclub', name='Test Club', is_active=True)
        User = get_user_model()
        self.user = User.objects.create_user(username='sharer', password='pass')
        Membership.objects.create(user=self.user, organization=self.org, is_approved=True)
        Season.objects.create(name='2026-27', start_year=2026, end_year=2027, is_current=True)
        self.url = reverse('content:image_share_target')
        # Enforce CSRF: el navegador NO envía token en el POST del share target;
        # si quitáramos csrf_exempt esto sería un 403 silencioso en producción.
        self.client = Client(enforce_csrf_checks=True)

    def _post_share(self, files, data=None, host='testclub.ilovevoley.es'):
        payload = dict(data or {})
        payload['image'] = files
        return self.client.post(self.url, payload, HTTP_HOST=host)

    def test_anonymous_post_renders_notice_and_stores_nothing(self):
        """Review focus 4: sin sesión no se retiene ningún archivo."""
        response = self._post_share([jpeg_bytes()])
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'inicia sesión')
        self.assertEqual(SharedUpload.objects.count(), 0)

    def test_root_domain_no_tenant_renders_notice(self):
        self.client.force_login(self.user)
        response = self._post_share([jpeg_bytes()], host='ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SharedUpload.objects.count(), 0)

    def test_single_image_stores_row_and_redirects_to_upload(self):
        """Review focus 1: POST multipart sin CSRF token debe ser aceptado."""
        self.client.force_login(self.user)
        response = self._post_share(
            [jpeg_bytes('IMG_1.jpg')], {'title': 'Partido de hoy', 'text': 'derbi'}
        )
        self.assertEqual(response.status_code, 302)
        row = SharedUpload.objects.get()
        self.assertEqual(str(row.owner), str(self.user))
        self.assertEqual(row.organization, self.org)
        self.assertEqual(row.original_name, 'IMG_1.jpg')
        self.assertEqual(row.content_type, 'image/jpeg')
        self.assertEqual(row.shared_title, 'Partido de hoy')
        self.assertEqual(row.shared_text, 'derbi')
        self.assertIn(f'share={row.token}', response['Location'])
        self.assertIn(reverse('content:image_upload'), response['Location'])

    def test_two_images_store_batch_and_redirect_to_bulk(self):
        self.client.force_login(self.user)
        response = self._post_share([jpeg_bytes('a.jpg'), jpeg_bytes('b.jpg')])
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SharedUpload.objects.count(), 2)
        batch = SharedUpload.objects.first().batch
        self.assertEqual(SharedUpload.objects.filter(batch=batch).count(), 2)
        self.assertIn(reverse('content:image_bulk_upload'), response['Location'])
        self.assertIn(f'share={batch}', response['Location'])

    def test_non_image_is_discarded(self):
        """Review focus 2."""
        self.client.force_login(self.user)
        bad = SimpleUploadedFile('nota.txt', b'hola', content_type='text/plain')
        response = self._post_share([bad])
        self.assertEqual(response.status_code, 200)  # página orientativa
        self.assertContains(response, 'No se admitió')
        self.assertEqual(SharedUpload.objects.count(), 0)

    def test_oversized_is_discarded(self):
        self.client.force_login(self.user)
        big = SimpleUploadedFile('grande.jpg', b'x' * (10 * 1024 * 1024 + 1), content_type='image/jpeg')
        response = self._post_share([big])
        self.assertEqual(SharedUpload.objects.count(), 0)
        self.assertContains(response, 'No se admitió')

    def test_more_than_twenty_files_keeps_first_twenty(self):
        """Review focus 5."""
        self.client.force_login(self.user)
        response = self._post_share([jpeg_bytes(f'f{i}.jpg') for i in range(21)])
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SharedUpload.objects.count(), 20)

    def test_expired_rows_purged_on_receive(self):
        """Limpieza oportunista con efecto persistente (guías: caso límite caro)."""
        self.client.force_login(self.user)
        stale = SharedUpload.objects.create(
            file=jpeg_bytes('vieja.jpg'), owner=self.user, organization=self.org,
            original_name='vieja.jpg', content_type='image/jpeg',
        )
        SharedUpload.objects.filter(pk=stale.pk).update(
            created_at=timezone.now() - timedelta(hours=25)
        )
        self._post_share([jpeg_bytes('nueva.jpg')])
        self.assertFalse(SharedUpload.objects.filter(pk=stale.pk).exists())
        self.assertTrue(SharedUpload.objects.filter(original_name='nueva.jpg').exists())
