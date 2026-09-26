"""Tests for Celery email notification tasks (issue #114 P0)."""
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

TINY_GIF = (
    b'GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00'
    b'\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00'
    b'\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b'
)

CELERY_EAGER = {
    'CELERY_TASK_ALWAYS_EAGER': True,
    'CELERY_TASK_EAGER_PROPAGATES': True,
}


@override_settings(
    NOTIFICATION_EMAIL_ENABLED=True,
    EMAIL_HOST_USER='noreply@test.com',
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    EMAIL_NOTIFICATIONS={'image_pending': True},
    **CELERY_EAGER,
)
class NotifyImagePendingTaskTest(TestCase):
    def setUp(self):
        from ilovevoley.core.models import Organization
        from ilovevoley.content.models import Image

        self.org = Organization.objects.create(slug='cluba', name='Club A')
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username='root', password='pass', email='root@test.com'
        )
        self.uploader = User.objects.create_user(
            username='uploader', password='pass', email='up@test.com', is_approved=True
        )
        self.Image = Image
        mail.outbox = []

    def _create_pending_image(self, **kwargs):
        defaults = {
            'image': SimpleUploadedFile('foto.jpg', TINY_GIF, content_type='image/jpeg'),
            'title': 'Foto pendiente',
            'uploaded_by': self.uploader,
            'organization': self.org,
            'status': 'pending',
        }
        defaults.update(kwargs)
        with self.captureOnCommitCallbacks(execute=True):
            return self.Image.objects.create(**defaults)

    def test_creating_pending_image_sends_email_via_celery_after_commit(self):
        self._create_pending_image()

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('pendiente de moderación', mail.outbox[0].subject.lower())
        self.assertEqual(mail.outbox[0].to, ['root@test.com'])

    def test_skip_flag_suppresses_individual_pending_email(self):
        image = self.Image(
            image=SimpleUploadedFile('foto.jpg', TINY_GIF, content_type='image/jpeg'),
            title='Skip',
            uploaded_by=self.uploader,
            organization=self.org,
            status='pending',
        )
        image._skip_pending_email = True
        with self.captureOnCommitCallbacks(execute=True):
            image.save()

        self.assertEqual(mail.outbox, [])

    def test_batch_notify_sends_single_email_for_multiple_images(self):
        from ilovevoley.core.tasks import notify_images_pending_batch_task

        ids = []
        for i in range(3):
            img = self.Image(
                image=SimpleUploadedFile(f'f{i}.jpg', TINY_GIF, content_type='image/jpeg'),
                title=f'Foto {i}',
                uploaded_by=self.uploader,
                organization=self.org,
                status='pending',
            )
            img._skip_pending_email = True
            with self.captureOnCommitCallbacks(execute=True):
                img.save()
            ids.append(img.id)

        mail.outbox = []
        notify_images_pending_batch_task(ids)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('3', mail.outbox[0].subject)
        body = mail.outbox[0].alternatives[0][0]
        self.assertIn('Foto 0', body)
        self.assertIn('Foto 2', body)


@override_settings(
    NOTIFICATION_EMAIL_ENABLED=True,
    EMAIL_HOST_USER='noreply@test.com',
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    GOOGLE_VISION_ENABLED=True,
    AUTO_MODERATION_ENABLED=True,
    **CELERY_EAGER,
)
class AnalyzeImageVisionTaskTest(TestCase):
    def setUp(self):
        from ilovevoley.core.models import Organization
        from ilovevoley.content.models import Image

        self.org = Organization.objects.create(slug='clubv', name='Club V')
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username='root', password='pass', email='root@test.com'
        )
        self.uploader = User.objects.create_user(
            username='uploader', password='pass', email='up@test.com', is_approved=True
        )
        self.Image = Image
        mail.outbox = []

    def test_vision_task_auto_approves_and_skips_pending_email(self):
        from unittest.mock import patch
        from ilovevoley.content.tasks import analyze_image_with_vision_task

        image = self.Image.objects.create(
            image=SimpleUploadedFile('foto.jpg', TINY_GIF, content_type='image/jpeg'),
            title='Safe',
            uploaded_by=self.uploader,
            organization=self.org,
            status='pending',
        )
        mail.outbox = []

        with patch(
            'ilovevoley.content.tasks.check_image_with_vision_api',
            return_value={
                'safe': True,
                'labels': ['volleyball'],
                'text': '',
                'details': {'api_response_ok': True},
            },
        ):
            analyze_image_with_vision_task(image.id, notify_if_pending=True)

        image.refresh_from_db()
        self.assertEqual(image.status, 'approved')
        self.assertTrue(image.vision_api_checked)
        self.assertEqual(mail.outbox, [])

    def test_vision_task_keeps_pending_and_notifies_when_requested(self):
        from unittest.mock import patch
        from ilovevoley.content.tasks import analyze_image_with_vision_task

        image = self.Image.objects.create(
            image=SimpleUploadedFile('foto.jpg', TINY_GIF, content_type='image/jpeg'),
            title='Needs review',
            uploaded_by=self.uploader,
            organization=self.org,
            status='pending',
        )
        mail.outbox = []

        with patch(
            'ilovevoley.content.tasks.check_image_with_vision_api',
            return_value={
                'safe': False,
                'labels': [],
                'text': '',
                'details': {'api_response_ok': True},
            },
        ), override_settings(EMAIL_NOTIFICATIONS={'image_pending': True}):
            analyze_image_with_vision_task(image.id, notify_if_pending=True)

        image.refresh_from_db()
        self.assertEqual(image.status, 'pending')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Needs review', mail.outbox[0].subject)


@override_settings(
    NOTIFICATION_EMAIL_ENABLED=True,
    EMAIL_HOST_USER='noreply@test.com',
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    **CELERY_EAGER,
)
class P1P2NotificationTasksTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='member', password='pass', email='member@test.com', is_approved=True
        )
        mail.outbox = []

    def test_notify_user_moderation_result_approved(self):
        from ilovevoley.core.tasks import notify_user_moderation_result_task

        notify_user_moderation_result_task(self.user.id, True, 'http://example.test/')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('aprobada', mail.outbox[0].subject.lower())
        self.assertEqual(mail.outbox[0].to, ['member@test.com'])

    def test_send_404_alert_task_sends_mail(self):
        from ilovevoley.core.tasks import send_404_immediate_alert_task

        send_404_immediate_alert_task(10, '12:00', '/missing', ['root@test.com'])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('404', mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, ['root@test.com'])

    def test_send_404_immediate_alert_enqueues_without_blocking(self):
        from unittest.mock import MagicMock, patch
        from ilovevoley.core.middleware import send_404_immediate_alert

        request = MagicMock()
        request.get_full_path.return_value = '/gone'

        with patch(
            'ilovevoley.core.middleware.get_admin_emails', return_value=['root@test.com']
        ), patch(
            'ilovevoley.core.middleware.cache'
        ) as mock_cache, patch(
            'ilovevoley.core.tasks.send_404_immediate_alert_task.delay'
        ) as mock_delay:
            mock_cache.get.return_value = 9  # next increment hits threshold 10
            result = send_404_immediate_alert(request, threshold=10)

        self.assertTrue(result)
        mock_delay.assert_called_once()
        self.assertEqual(mail.outbox, [])
