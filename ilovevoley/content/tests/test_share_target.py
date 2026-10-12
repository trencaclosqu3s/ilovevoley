"""Tests del share target PWA (#524).

Justificación (docs/ai-guidelines/testing-guidelines.md): flujo nuevo con efectos
persistentes (filas SharedUpload + archivos en MEDIA), gate de autenticación y
validación de tipos/tamaños contra una entrada (POST sin CSRF desde el SO) que
solo puede romperse en producción.
"""
import shutil
import tempfile
import uuid as uuid_mod
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

    def test_unapproved_membership_is_rejected_without_storing(self):
        """Gate de membresía del receptor (decisión de diseño registrada en el
        plan): un miembro pendiente no puede acumular archivos en MEDIA."""
        Membership.objects.filter(user=self.user, organization=self.org).update(is_approved=False)
        self.client.force_login(self.user)
        response = self._post_share([jpeg_bytes()])
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
        stale_path = stale.file.name
        self._post_share([jpeg_bytes('nueva.jpg')])
        self.assertFalse(SharedUpload.objects.filter(pk=stale.pk).exists())
        self.assertTrue(SharedUpload.objects.filter(original_name='nueva.jpg').exists())
        # El archivo físico también desaparece: la promesa de "24 h" incluye el disco.
        from django.core.files.storage import default_storage
        self.assertFalse(default_storage.exists(stale_path))


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'])
class ShareTargetSingleUploadTests(TestCase):
    """Consumo del token: efectos persistentes reales (Image creada, fila borrada)
    y rechazo de tokens ajenos (guía: camino crítico + idempotencia del intentado
    fallido)."""

    def setUp(self):
        from ilovevoley.users.models import Membership

        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media_root)
        override.enable()
        self.addCleanup(override.disable)
        cache.clear()

        self.org = Organization.objects.create(slug='testclub', name='Test Club', is_active=True)
        User = get_user_model()
        self.user = User.objects.create_user(username='sharer', password='pass')
        self.other = User.objects.create_user(username='other', password='pass')
        Membership.objects.create(user=self.user, organization=self.org, is_approved=True)
        Season.objects.create(name='2026-27', start_year=2026, end_year=2027, is_current=True)
        self.client.force_login(self.user)

    def _make_row(self, owner=None, org=None):
        return SharedUpload.objects.create(
            file=jpeg_bytes('IMG_9.jpg'),
            owner=owner or self.user,
            organization=org or self.org,
            original_name='IMG_9.jpg',
            content_type='image/jpeg',
            shared_title='IMG_9',
        )

    def test_get_share_previews_image_and_hides_file_input(self):
        row = self._make_row()
        response = self.client.get(
            reverse('content:image_upload'), {'share': str(row.token)},
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertContains(response, 'share_token')
        self.assertContains(response, row.file.url)

    def test_get_share_foreign_token_falls_back_to_plain_form(self):
        """Review focus 3: token de otro usuario → formulario normal, sin imagen."""
        row = self._make_row(owner=self.other)
        response = self.client.get(
            reverse('content:image_upload'), {'share': str(row.token)},
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertNotContains(response, 'name="share_token"')
        self.assertContains(response, 'no es válido')

    def test_post_with_share_token_creates_image_and_deletes_row(self):
        row = self._make_row()
        row_path = row.file.name
        response = self.client.post(
            reverse('content:image_upload'),
            {'share_token': str(row.token), 'image_type': 'match'},
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 302)
        from ilovevoley.content.models import Image as ImageModel
        created = ImageModel.objects.get()
        self.assertEqual(created.uploaded_by, self.user)
        self.assertEqual(created.organization, self.org)
        self.assertFalse(SharedUpload.objects.filter(pk=row.pk).exists())
        from django.core.files.storage import default_storage
        self.assertFalse(default_storage.exists(row_path))

    def test_post_with_invalid_token_does_not_create_anything(self):
        import uuid as uuid_mod
        from ilovevoley.content.models import Image as ImageModel
        response = self.client.post(
            reverse('content:image_upload'),
            {'share_token': str(uuid_mod.uuid4()), 'image_type': 'match'},
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(ImageModel.objects.count(), 0)


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'])
class ShareTargetBulkUploadTests(TestCase):
    """Lote consumido desde batch: múltiples filas -> múltiples Images y limpieza
    (guía: flujo con efectos persistentes)."""

    setUp = ShareTargetSingleUploadTests.setUp

    def _make_rows(self, n):
        batch = uuid_mod.uuid4()
        rows = [
            SharedUpload.objects.create(
                batch=batch, file=jpeg_bytes(f'IMG_{i}.jpg'), owner=self.user,
                organization=self.org, original_name=f'IMG_{i}.jpg',
                content_type='image/jpeg',
            )
            for i in range(n)
        ]
        return batch, rows

    def test_get_share_batch_previews_all(self):
        batch, rows = self._make_rows(2)
        response = self.client.get(
            reverse('content:image_bulk_upload'), {'share': str(batch)},
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertContains(response, 'share_batch')
        self.assertContains(response, rows[0].file.url)
        self.assertContains(response, rows[1].file.url)

    def test_post_with_share_batch_creates_images_and_deletes_rows(self):
        batch, rows = self._make_rows(2)
        response = self.client.post(
            reverse('content:image_bulk_upload'),
            {'share_batch': str(batch), 'image_type': 'training'},
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 302)
        from ilovevoley.content.models import Image as ImageModel
        self.assertEqual(ImageModel.objects.filter(organization=self.org).count(), 2)
        self.assertEqual(SharedUpload.objects.filter(batch=batch).count(), 0)

    def test_bulk_all_failed_keeps_rows_and_returns_to_share(self):
        """Spec §6: si ninguna imagen se crea, el lote sobrevive para reintentar."""
        big = SimpleUploadedFile('grande.jpg', b'x' * (10 * 1024 * 1024 + 1), content_type='image/jpeg')
        batch = uuid_mod.uuid4()
        row = SharedUpload.objects.create(
            batch=batch, file=big, owner=self.user, organization=self.org,
            original_name='grande.jpg', content_type='image/jpeg',
        )
        response = self.client.post(
            reverse('content:image_bulk_upload'),
            {'share_batch': str(batch), 'image_type': 'training'},
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(f'share={batch}', response['Location'])
        self.assertTrue(SharedUpload.objects.filter(pk=row.pk).exists())

    def test_post_with_foreign_batch_creates_nothing(self):
        """Review focus 3 en lote: batch de otro usuario es ignorado."""
        from ilovevoley.content.models import Image as ImageModel
        response = self.client.post(
            reverse('content:image_bulk_upload'),
            {'share_batch': str(uuid_mod.uuid4()), 'image_type': 'training'},
            HTTP_HOST='testclub.ilovevoley.es',
            follow=True,
        )
        self.assertEqual(ImageModel.objects.count(), 0)
        self.assertEqual(
            [m.message for m in response.context['messages']],
            ['El enlace de las fotos compartidas ya no es válido.'],
        )
