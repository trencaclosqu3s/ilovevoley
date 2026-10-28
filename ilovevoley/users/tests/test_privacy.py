from datetime import timedelta
import json
import tempfile
from unittest.mock import patch
import zipfile
from io import BytesIO

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image as PilImage

from ilovevoley.competitions.models.competitions import Match
from ilovevoley.competitions.models.story import StoryComposition
from ilovevoley.content.models import (
    Comment, Image, ImageFavorite, ImageRemovalRequest, SharedUpload, Video,
)
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.rosters.models import Person, PlayerRole
from ilovevoley.teams.models import Club, Team
from ilovevoley.teams.tests.helpers import identity_of
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
    ErasureRefused,
    active_export_for,
    apply_erasure,
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


HOST = 'club-a.ilovevoley.es'


@override_settings(ALLOWED_HOSTS=[HOST, 'localhost'])
class ExportViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username='ana', password='pass', email='ana@example.com',
        )
        self.org = Organization.objects.create(slug='club-a', name='Club A')
        Membership.objects.create(
            user=self.user, organization=self.org, role='member', is_approved=True,
        )
        self.client.force_login(self.user)

    def test_second_post_does_not_create_another_export(self):
        url = reverse('request_data_export')
        self.client.post(url, HTTP_HOST=HOST)
        self.client.post(url, HTTP_HOST=HOST)
        self.assertEqual(DataExport.objects.filter(user=self.user).count(), 1)
        self.assertEqual(
            DataExport.objects.get(user=self.user).status, DataExport.Status.PENDING,
        )

    def test_bad_token_does_not_return_the_zip(self):
        export = DataExport.objects.create(
            user=self.user, status=DataExport.Status.READY,
            expires_at=timezone.now() + timedelta(days=1),
        )
        export.file.save('listo.zip', ContentFile(b'PK\x03\x04datos'), save=True)
        bad = self.client.get(
            reverse('download_data_export', args=['token-malo']), HTTP_HOST=HOST,
        )
        self.assertNotIn(b'PK\x03\x04datos', bad.content)
        good = self.client.get(
            reverse('download_data_export', args=[generate_export_token(export)]),
            HTTP_HOST=HOST,
        )
        good_content = (
            b''.join(good.streaming_content)
            if hasattr(good, 'streaming_content')
            else good.content
        )
        self.assertIn(b'PK\x03\x04datos', good_content)

    def test_ready_export_without_file_does_not_serve_bytes(self):
        export = DataExport.objects.create(
            user=self.user, status=DataExport.Status.READY,
            expires_at=timezone.now() + timedelta(days=1),
        )
        response = self.client.get(
            reverse('download_data_export', args=[generate_export_token(export)]),
            HTTP_HOST=HOST,
        )
        self.assertNotIn(b'PK\x03\x04', response.content)

    def test_media_url_does_not_serve_the_export(self):
        export = DataExport.objects.create(
            user=self.user, status=DataExport.Status.READY,
            expires_at=timezone.now() + timedelta(days=1),
        )
        export.file.save('listo.zip', ContentFile(b'PK\x03\x04datos'), save=True)
        response = self.client.get('/media/' + export.file.name, HTTP_HOST=HOST)
        self.assertNotIn(b'PK\x03\x04datos', response.content)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ErasureTests(TestCase):
    def _user(self, username, **kwargs):
        return get_user_model().objects.create_user(
            username=username,
            password='pass',
            email=f'{username}@example.com',
            **kwargs,
        )

    def _jpeg_image(self, user, title, organization, **kwargs):
        return Image.objects.create(
            image=tiny_jpeg(f'{title}.jpg'),
            title=title,
            uploaded_by=user,
            organization=organization,
            status='approved',
            **kwargs,
        )

    def test_unapproved_or_inactive_admin_does_not_unblock(self):
        user = self._user('admin-a')
        org = Organization.objects.create(slug='solo', name='Solo')
        Membership.objects.create(user=user, organization=org, role='admin', is_approved=True)
        other = self._user('other-admin')
        Membership.objects.create(user=other, organization=org, role='admin', is_approved=False)

        with self.assertRaises(ErasureRefused) as blocked:
            apply_erasure(user, 'retain')
        self.assertEqual(blocked.exception.code, 'last_admin')
        user.refresh_from_db()
        self.assertEqual(user.email, 'admin-a@example.com')

        other.is_active = False
        other.save(update_fields=['is_active'])
        Membership.objects.filter(user=other).update(is_approved=True)
        with self.assertRaises(ErasureRefused):
            apply_erasure(user, 'retain')

        keeper = self._user('keeper')
        Membership.objects.create(user=keeper, organization=org, role='admin', is_approved=True)
        apply_erasure(user, 'retain')
        user.refresh_from_db()
        self.assertTrue(is_erased(user))

    def test_last_admin_of_one_club_blocks_the_whole_account(self):
        user = self._user('multi')
        org_a = Organization.objects.create(slug='club-sola', name='Sola')
        org_b = Organization.objects.create(slug='club-b2', name='Club B')
        Membership.objects.create(user=user, organization=org_a, role='admin', is_approved=True)
        Membership.objects.create(user=user, organization=org_b, role='member', is_approved=True)
        other = self._user('admin-b')
        Membership.objects.create(user=other, organization=org_b, role='admin', is_approved=True)

        with self.assertRaises(ErasureRefused):
            apply_erasure(user, 'delete')

        self.assertTrue(Membership.objects.filter(user=user, organization=org_b).exists())
        user.refresh_from_db()
        self.assertEqual(user.email, 'multi@example.com')

    def test_staff_and_superuser_are_refused(self):
        staff = self._user('staffer', is_staff=True)
        root = get_user_model().objects.create_superuser(username='root', password='pass', email='root@example.com')
        with self.assertRaises(ErasureRefused) as staff_block:
            apply_erasure(staff, 'delete')
        with self.assertRaises(ErasureRefused) as root_block:
            apply_erasure(root, 'delete')
        self.assertEqual(staff_block.exception.code, 'staff')
        self.assertEqual(root_block.exception.code, 'staff')
        staff.refresh_from_db()
        root.refresh_from_db()
        self.assertEqual(staff.email, 'staffer@example.com')
        self.assertEqual(root.email, 'root@example.com')

    def test_unlinks_children_and_keeps_the_sporting_record(self):
        user = self._user('madre', first_name='Ana')
        other = self._user('padre')
        org = Organization.objects.create(slug='club-ficha', name='Ficha')
        Membership.objects.create(user=user, organization=org, role='member', is_approved=True)
        category = Category.objects.create(name='Alevin 613')
        club = Club.objects.create(federation_id='C-613-ROLE', official_name='Club Rol')
        team = Team.objects.create(
            name='Alevin A', federation_id='T-613-ROLE', category=category, club=club,
        )
        own = Person.objects.create(
            first_name='Ana', last_name='Serra', birth_year=1990, user=user,
            notes='nota del club', image_consent=Person.ImageConsent.FULL_PUBLIC,
        )
        role = PlayerRole.objects.create(
            person=own, identity=identity_of(team), season=Season.objects.resolve('2025-26'),
            jersey_number=7,
        )
        child = Person.objects.create(
            first_name='Laia', last_name='Serra', birth_year=2014,
            image_consent=Person.ImageConsent.INTERNAL_ONLY,
        )
        user.children.add(child)
        other.children.add(child)

        apply_erasure(user, 'retain')

        own.refresh_from_db()
        child.refresh_from_db()
        self.assertIsNone(own.user_id)
        self.assertEqual(own.notes, 'nota del club')
        self.assertEqual(own.image_consent, Person.ImageConsent.FULL_PUBLIC)
        self.assertTrue(PlayerRole.objects.filter(pk=role.pk).exists())
        self.assertTrue(other.children.filter(pk=child.pk).exists())
        self.assertFalse(user.children.filter(pk=child.pk).exists())

    def test_anonymizes_every_club(self):
        user = self._user('ana-clubs', first_name='Ana', last_name='Serra', parent_info='madre')
        user.calendar_token = 'cal-token-ana'
        user.avatar.save('avatar.jpg', tiny_jpeg('avatar.jpg'), save=True)
        org_a = Organization.objects.create(slug='org-a613', name='A')
        org_b = Organization.objects.create(slug='org-b613', name='B')
        Membership.objects.create(user=user, organization=org_a, role='member', is_approved=True)
        Membership.objects.create(user=user, organization=org_b, role='manager', is_approved=True)
        SocialAccount.objects.create(user=user, provider='google', uid='google-ana')
        EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
        WebPushSubscription.objects.create(
            user=user, organization=org_a, endpoint='https://push.example/ana-613',
            p256dh='p256', auth='auth',
        )

        apply_erasure(user, 'retain')
        user.refresh_from_db()

        self.assertEqual(user.username, f'deleted-{user.pk}')
        self.assertEqual(user.email, '')
        self.assertEqual(user.first_name, '')
        self.assertEqual(user.parent_info, '')
        self.assertIsNone(user.calendar_token)
        self.assertFalse(user.avatar)
        self.assertFalse(user.is_active)
        self.assertFalse(Membership.objects.filter(user=user).exists())
        self.assertFalse(SocialAccount.objects.filter(uid='google-ana').exists())
        self.assertFalse(EmailAddress.objects.filter(user=user).exists())
        self.assertFalse(WebPushSubscription.objects.filter(endpoint='https://push.example/ana-613').exists())
        event = PrivacyAuditEvent.objects.get(action=PrivacyAuditEvent.Action.ERASURE)
        blob = json.dumps({
            'user_id': event.user_id,
            'action': event.action,
            'content_choice': event.content_choice,
            'club_count': event.club_count,
        })
        self.assertEqual(event.user_id, user.pk)
        self.assertEqual(event.content_choice, 'retain')
        self.assertEqual(event.club_count, 2)
        self.assertNotIn('ana-clubs@example.com', blob)
        self.assertNotIn('Ana', blob)

    def test_delete_removes_own_files_and_retain_clears_author(self):
        owner = self._user('owner')
        other = self._user('other-photo')
        org = Organization.objects.create(slug='album-613', name='Album')
        album = '11111111-1111-1111-1111-111111111111'
        mine = self._jpeg_image(owner, 'Mia', org, album_group_id=album)
        theirs = self._jpeg_image(other, 'Suya', org, album_group_id=album)
        mine_name = mine.image.name
        my_video = Video.objects.create(
            title='Mio', youtube_url='https://youtu.be/mio613', created_by=owner, organization=org,
        )
        their_video = Video.objects.create(
            title='Suyo', youtube_url='https://youtu.be/suyo613', created_by=other, organization=org,
        )

        apply_erasure(owner, 'delete')

        self.assertFalse(Image.objects.filter(pk=mine.pk).exists())
        self.assertFalse(default_storage.exists(mine_name))
        self.assertTrue(Image.objects.filter(pk=theirs.pk).exists())
        self.assertFalse(Video.objects.filter(pk=my_video.pk).exists())
        their_video.refresh_from_db()
        self.assertEqual(their_video.youtube_url, 'https://youtu.be/suyo613')

        kept = self._jpeg_image(other, 'Conservada', org)
        kept_name = kept.image.name
        kept_video = Video.objects.create(
            title='Conservado', youtube_url='https://youtu.be/keep613', created_by=other, organization=org,
        )
        apply_erasure(other, 'retain')
        kept.refresh_from_db()
        kept_video.refresh_from_db()
        self.assertIsNone(kept.uploaded_by_id)
        self.assertIsNone(kept_video.created_by_id)
        self.assertTrue(default_storage.exists(kept_name))

    def test_second_erasure_does_not_touch_authorless_images(self):
        first = self._user('first')
        second = self._user('second')
        org = Organization.objects.create(slug='null-author', name='Null')
        kept = self._jpeg_image(first, 'Sin autor', org)
        apply_erasure(first, 'retain')
        kept.refresh_from_db()
        self.assertIsNone(kept.uploaded_by_id)
        image_count = Image.objects.count()
        apply_erasure(first, 'delete')
        first.refresh_from_db()
        self.assertEqual(first.username, f'deleted-{first.pk}')
        self.assertEqual(Image.objects.count(), image_count)
        disposable = self._jpeg_image(second, 'De B', org)
        apply_erasure(second, 'delete')
        self.assertTrue(Image.objects.filter(pk=kept.pk).exists())
        self.assertFalse(Image.objects.filter(pk=disposable.pk).exists())

    def test_comments_favorites_stories_and_shared_uploads_go(self):
        user = self._user('comenta')
        author = self._user('autor-video')
        org = Organization.objects.create(slug='comments-613', name='Comments')
        video = Video.objects.create(
            title='Ajeno', youtube_url='https://youtu.be/ajeno', created_by=author, organization=org,
        )
        Comment.objects.create(video=video, user=user, content='hola')
        image = self._jpeg_image(author, 'Favorita', org)
        ImageFavorite.objects.create(image=image, user=user)
        match = Match.objects.create(
            match_date=timezone.now(), is_friendly=True,
            home_team_text='Local', away_team_text='Visitante',
        )
        StoryComposition.objects.create(
            user=user, organization=org, match=match, image=image, layout={},
        )
        SharedUpload.objects.create(
            file=tiny_jpeg('shared.jpg'), owner=user, organization=org,
        )

        apply_erasure(user, 'retain')

        self.assertFalse(Comment.objects.filter(user=user).exists())
        self.assertTrue(Video.objects.filter(pk=video.pk).exists())
        self.assertFalse(ImageFavorite.objects.filter(user=user).exists())
        self.assertFalse(StoryComposition.objects.filter(user=user).exists())
        self.assertFalse(SharedUpload.objects.filter(owner=user).exists())

    def test_removal_request_loses_requester_and_reason(self):
        user = self._user('pide')
        org = Organization.objects.create(slug='removal-613', name='Removal')
        request = ImageRemovalRequest.objects.create(
            organization=org, image_title='Foto', requested_by=user, reason='es mi hija',
        )
        apply_erasure(user, 'retain')
        request.refresh_from_db()
        self.assertIsNone(request.requested_by_id)
        self.assertEqual(request.reason, '')

    def test_moderated_image_stays(self):
        moderator = self._user('modera')
        author = self._user('sube')
        org = Organization.objects.create(slug='mod-613', name='Mod')
        image = self._jpeg_image(author, 'Moderada', org)
        image.moderated_by = moderator
        image.save(update_fields=['moderated_by'])

        apply_erasure(moderator, 'retain')
        image.refresh_from_db()
        self.assertIsNone(image.moderated_by_id)
        self.assertEqual(image.uploaded_by_id, author.pk)

    def test_failure_rolls_back_rows_and_keeps_the_file(self):
        user = self._user('rollback')
        org = Organization.objects.create(slug='roll-613', name='Roll')
        Membership.objects.create(user=user, organization=org, role='member', is_approved=True)
        image = self._jpeg_image(user, 'Queda', org)
        image_name = image.image.name
        video = Video.objects.create(
            title='Hilo', youtube_url='https://youtu.be/hilo', created_by=user, organization=org,
        )
        Comment.objects.create(video=video, user=user, content='no borrar')

        with patch(
            'ilovevoley.users.privacy.PrivacyAuditEvent.objects.create',
            side_effect=RuntimeError('db'),
        ):
            with self.assertRaises(RuntimeError):
                apply_erasure(user, 'delete')

        user.refresh_from_db()
        self.assertEqual(user.email, 'rollback@example.com')
        self.assertTrue(Comment.objects.filter(user=user).exists())
        self.assertTrue(Membership.objects.filter(user=user).exists())
        self.assertTrue(Image.objects.filter(pk=image.pk).exists())
        self.assertTrue(default_storage.exists(image_name))



