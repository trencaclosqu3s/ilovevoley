from datetime import timedelta
import json
from unittest.mock import patch
import zipfile
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image as PilImage

from ilovevoley.content.models import Image, Video
from ilovevoley.core.models import Category, Organization
from ilovevoley.rosters.models import Person
from ilovevoley.teams.models import Team
from ilovevoley.users.models import (
    CategoryPreference,
    DataExport,
    Membership,
    NotificationPreference,
    NotificationType,
    PrivacyAuditEvent,
    WebPushSubscription,
)
from ilovevoley.users.privacy import (
    active_export_for,
    build_export_zip,
    cleanup_expired_data_exports,
    cleanup_expired_privacy_audit_events,
    export_for_token,
    generate_export_token,
    is_erased,
)
from ilovevoley.users.tasks import build_data_export_task


class ExportWindowTests(TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='ana', password='pass', email='ana@example.com',
        )

    def test_pending_older_than_one_hour_does_not_block(self):
        old = DataExport.objects.create(user=self.user, status=DataExport.Status.PENDING)
        DataExport.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(hours=2),
        )
        fresh = DataExport.objects.create(
            user=self.user,
            status=DataExport.Status.READY,
            expires_at=timezone.now() + timedelta(days=1),
        )

        self.assertEqual(active_export_for(self.user).pk, fresh.pk)
        old.refresh_from_db()
        self.assertEqual(old.status, DataExport.Status.FAILED)

    def test_erased_marker_is_the_deleted_username(self):
        self.assertFalse(is_erased(self.user))
        self.user.username = f'deleted-{self.user.pk}'
        self.assertTrue(is_erased(self.user))


def tiny_jpeg(name='foto.jpg'):
    buf = BytesIO()
    PilImage.new('RGB', (8, 8), 'red').save(buf, format='JPEG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/jpeg')


class ExportZipTests(TestCase):
    def test_zip_lists_both_clubs_and_omits_secrets(self):
        user = get_user_model().objects.create_user(
            username='ana', password='pass-secreto-613', email='ana@example.com',
            first_name='Ana', last_name='Serra', parent_info='madre de Laia',
        )
        user.calendar_token = 'cal-token-secreto'
        user.save(update_fields=['calendar_token'])
        org_a = Organization.objects.create(slug='club-a', name='Club A')
        org_b = Organization.objects.create(slug='club-b', name='Club B')
        Membership.objects.create(user=user, organization=org_a, role='member', is_approved=True)
        Membership.objects.create(user=user, organization=org_b, role='admin', is_approved=True)
        category = Category.objects.create(name='Infantil')
        team = Team.objects.create(name='Infantil A', federation_id='T-613-A', category=category)
        pref = CategoryPreference.objects.create(user=user, organization=org_a)
        pref.categories.add(category)
        pref.teams.add(team)
        NotificationPreference.objects.create(
            user=user, organization=org_a,
            notification_type=NotificationType.MATCH_RESULT, is_enabled=False,
        )
        child = Person.objects.create(
            first_name='Laia', last_name='Serra', birth_year=2014,
            image_consent=Person.ImageConsent.FULL_PUBLIC,
        )
        user.children.add(child)
        WebPushSubscription.objects.create(
            user=user, organization=org_a, endpoint='https://push.example/ana',
            p256dh='p256-secreto', auth='push-auth-secreto',
        )
        Image.objects.create(
            image=tiny_jpeg(), title='Foto de Laia', uploaded_by=user,
            organization=org_a, status='approved',
        )
        Video.objects.create(
            title='Set 1', youtube_url='https://youtu.be/abc123',
            created_by=user, organization=org_b,
        )

        with zipfile.ZipFile(BytesIO(build_export_zip(user))) as archive:
            names = set(archive.namelist())
            account = json.loads(archive.read('account.json'))
            content = json.loads(archive.read('content.json'))
            account_csv = archive.read('account.csv').decode()
            raw = archive.read('account.json') + archive.read('content.json') + archive.read('account.csv') + archive.read('content.csv')

        self.assertEqual(names, {'account.json', 'account.csv', 'content.json', 'content.csv'})
        self.assertEqual({row['organization'] for row in account['memberships']}, {'Club A', 'Club B'})
        self.assertEqual(account['profile']['email'], 'ana@example.com')
        self.assertEqual(account['category_preferences'][0]['teams'], ['Infantil A'])
        self.assertFalse(account['notification_preferences'][0]['is_enabled'])
        self.assertEqual(account['persons'][0]['first_name'], 'Laia')
        self.assertEqual(account['persons'][0]['image_consent'], Person.ImageConsent.FULL_PUBLIC)
        self.assertEqual(content['images'][0]['title'], 'Foto de Laia')
        self.assertEqual(content['videos'][0]['youtube_url'], 'https://youtu.be/abc123')
        self.assertIn('Laia', account_csv)
        self.assertNotIn(b'cal-token-secreto', raw)
        self.assertNotIn(b'push-auth-secreto', raw)
        self.assertNotIn(b'pass-secreto-613', raw)
        self.assertNotIn(b'p256-secreto', raw)


@override_settings(
    NOTIFICATION_EMAIL_ENABLED=True,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    EMAIL_HOST_USER='test@example.com',
)
class ExportTaskTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='ana', password='pass', email='ana@example.com',
        )
        self.org = Organization.objects.create(slug='club-a', name='Club A')

    def test_ready_export_emails_a_link_and_audits_without_user_id(self):
        export = DataExport.objects.create(user=self.user, status=DataExport.Status.PENDING)
        build_data_export_task(export.pk, self.org.pk)
        export.refresh_from_db()
        self.assertEqual(export.status, DataExport.Status.READY)
        self.assertTrue(export.file)
        self.assertIsNotNone(export_for_token(generate_export_token(export)))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('/profile/exportar/', mail.outbox[0].body)
        event = PrivacyAuditEvent.objects.get()
        self.assertEqual(event.action, PrivacyAuditEvent.Action.EXPORT)
        self.assertIsNone(event.user_id)

    def test_task_stops_when_the_account_is_already_erased(self):
        self.user.username = f'deleted-{self.user.pk}'
        self.user.save(update_fields=['username'])
        export = DataExport.objects.create(user=self.user, status=DataExport.Status.PENDING)
        build_data_export_task(export.pk, None)
        export.refresh_from_db()
        self.assertEqual(export.status, DataExport.Status.PENDING)
        self.assertFalse(export.file)
        self.assertEqual(len(mail.outbox), 0)

    def test_failed_build_leaves_no_file(self):
        export = DataExport.objects.create(user=self.user, status=DataExport.Status.PENDING)
        with patch('ilovevoley.users.tasks.build_export_zip', side_effect=RuntimeError('disk')):
            build_data_export_task(export.pk, None)
        export.refresh_from_db()
        self.assertEqual(export.status, DataExport.Status.FAILED)
        self.assertFalse(export.file)
        self.assertEqual(len(mail.outbox), 1)

    def test_cleanup_drops_expired_ready_and_old_failed(self):
        ready = DataExport.objects.create(
            user=self.user, status=DataExport.Status.READY,
            expires_at=timezone.now() - timedelta(days=1),
        )
        ready.file.save('viejo.zip', ContentFile(b'PK'), save=True)
        failed = DataExport.objects.create(user=self.user, status=DataExport.Status.FAILED)
        DataExport.objects.filter(pk=failed.pk).update(
            created_at=timezone.now() - timedelta(days=8),
        )
        pending = DataExport.objects.create(user=self.user, status=DataExport.Status.PENDING)
        DataExport.objects.filter(pk=pending.pk).update(
            created_at=timezone.now() - timedelta(hours=2),
        )
        old_event = PrivacyAuditEvent.objects.create(action=PrivacyAuditEvent.Action.EXPORT)
        PrivacyAuditEvent.objects.filter(pk=old_event.pk).update(
            created_at=timezone.now() - timedelta(days=366),
        )

        cleanup_expired_data_exports()
        cleanup_expired_privacy_audit_events()

        self.assertFalse(DataExport.objects.filter(pk=ready.pk).exists())
        self.assertFalse(DataExport.objects.filter(pk=failed.pk).exists())
        pending.refresh_from_db()
        self.assertEqual(pending.status, DataExport.Status.FAILED)
        self.assertFalse(PrivacyAuditEvent.objects.filter(pk=old_event.pk).exists())

    def test_expired_token_does_not_resolve(self):
        export = DataExport.objects.create(
            user=self.user, status=DataExport.Status.READY,
            expires_at=timezone.now() + timedelta(days=1),
        )
        export.file.save('listo.zip', ContentFile(b'PK'), save=True)
        token = generate_export_token(export)
        export.expires_at = timezone.now() - timedelta(seconds=1)
        export.save(update_fields=['expires_at'])
        self.assertIsNone(export_for_token(token))
        self.assertIsNone(export_for_token('no-es-un-token'))


