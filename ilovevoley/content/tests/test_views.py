from django.test import SimpleTestCase, TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

import re


def _count_script(content, needle):
    """Cuenta etiquetas <script src> que referencian ``needle`` tolerando el
    hash de ``ManifestStaticFilesStorage``."""
    return len(re.findall(rb'<script[^>]+src="[^"]*' + needle.encode() + rb'[^"]*"', content))

from ilovevoley.core.models import Organization, Season
from ilovevoley.content import forms as content_forms
from ilovevoley.content import views as content_views
from ilovevoley.content.models import Image, ImageFavorite, Video
from ilovevoley.videos.forms import content as videos_forms_content
from ilovevoley.videos.views import content as videos_views_content
from ilovevoley.videos.views import moderation as videos_views_moderation

TINY_GIF = (
    b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
    b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00'
    b'\x00\x02\x02D\x01\x00;'
)


class ContentReExportCompatibilityTest(SimpleTestCase):
    """Verifica que las importaciones históricas desde videos sigan funcionando."""

    def test_forms_are_reexported(self):
        self.assertIs(videos_forms_content.VideoForm, content_forms.VideoForm)
        self.assertIs(videos_forms_content.CommentForm, content_forms.CommentForm)
        self.assertIs(videos_forms_content.ImageUploadForm, content_forms.ImageUploadForm)
        self.assertIs(videos_forms_content.ImageModerationForm, content_forms.ImageModerationForm)
        self.assertIs(videos_forms_content.ImageFilterForm, content_forms.ImageFilterForm)
        self.assertIs(videos_forms_content.VideoEntryForm, content_forms.VideoEntryForm)
        self.assertIs(videos_forms_content.VideoEntryFormSet, content_forms.VideoEntryFormSet)
        self.assertIs(videos_forms_content.VideoBulkSharedForm, content_forms.VideoBulkSharedForm)

    def test_views_are_reexported(self):
        self.assertIs(videos_views_content.video_list, content_views.video_list)
        self.assertIs(videos_views_content.video_detail, content_views.video_detail)
        self.assertIs(videos_views_content.video_create, content_views.video_create)
        self.assertIs(videos_views_content.video_bulk_create, content_views.video_bulk_create)
        self.assertIs(videos_views_content.image_gallery, content_views.image_gallery)
        self.assertIs(videos_views_content.image_gallery_albums, content_views.image_gallery_albums)
        self.assertIs(videos_views_content.image_upload, content_views.image_upload)
        self.assertIs(videos_views_content.image_bulk_upload, content_views.image_bulk_upload)
        self.assertIs(videos_views_content.image_detail, content_views.image_detail)
        self.assertIs(videos_views_content.match_images, content_views.match_images)
        self.assertIs(videos_views_content.album_group_images, content_views.album_group_images)
        self.assertIs(videos_views_moderation.image_moderation, content_views.image_moderation)
        self.assertIs(videos_views_moderation.image_moderate_action, content_views.image_moderate_action)
        self.assertIs(videos_views_moderation.image_moderate_bulk, content_views.image_moderate_bulk)
        self.assertIs(videos_views_moderation.moderate_image_api, content_views.moderate_image_api)


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'])
class ContentViewUrlTests(TestCase):
    def setUp(self):
        from ilovevoley.users.models import Membership
        cache.clear()
        self.org = Organization.objects.create(
            slug='testclub', name='Test Club', is_active=True
        )
        User = get_user_model()
        self.user = User.objects.create_user(username='member', password='pass')
        Membership.objects.create(
            user=self.user, organization=self.org, is_approved=True
        )

    def test_image_moderation_requires_staff(self):
        url = reverse('content:image_moderation')
        # Anónimo redirige a login
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

        # Usuario normal recibe 403
        self.client.force_login(self.user)
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 403)

        # Usuario superusuario pasa con 200
        self.user.is_superuser = True
        self.user.save()
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'content/image_moderation.html')

        # Tenant admin pasa con 200 sin ser superusuario
        from ilovevoley.users.models import Membership
        self.user.is_superuser = False
        self.user.save()
        Membership.objects.filter(user=self.user, organization=self.org).update(role='admin')
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)

        # Usuario con is_staff=True pero rol member en el tenant recibe 403
        Membership.objects.filter(user=self.user, organization=self.org).update(role='member')
        self.user.is_staff = True
        self.user.save()
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 403)



@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'])
class ContentSeasonFilterTests(TestCase):
    """Vídeos y galería filtran por temporada activa por defecto."""

    def setUp(self):
        from ilovevoley.users.models import Membership
        cache.clear()
        self.org = Organization.objects.create(slug='testclub', name='Test Club', is_active=True)
        User = get_user_model()
        self.user = User.objects.create_user(username='member', password='pass')
        Membership.objects.create(user=self.user, organization=self.org, is_approved=True)
        self.current = Season.objects.create(
            name='2026-27', start_year=2026, end_year=2027, is_current=True
        )
        self.past = Season.objects.create(name='2025-26', start_year=2025, end_year=2026)
        Video.objects.create(
            title='Actual', youtube_url='https://youtu.be/a', created_by=self.user,
            organization=self.org, season=self.current,
        )
        Video.objects.create(
            title='Pasado', youtube_url='https://youtu.be/b', created_by=self.user,
            organization=self.org, season=self.past,
        )
        for title, season, filename in (('Actual', self.current, 'a.jpg'), ('Pasado', self.past, 'b.jpg')):
            Image.objects.create(
                image=SimpleUploadedFile(filename, TINY_GIF, content_type='image/jpeg'),
                title=title, uploaded_by=self.user, organization=self.org,
                status='approved', season=season,
            )

    def _titles(self, response):
        return {obj.title for obj in response.context['page_obj'].object_list}

    def test_video_list_default_muestra_temporada_activa(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('content:video_list'), HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(self._titles(response), {'Actual'})

    def test_video_list_filtra_temporada_pasada(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse('content:video_list') + f'?season={self.past.id}',
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(self._titles(response), {'Pasado'})

    def test_video_list_todas_las_temporadas(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse('content:video_list') + '?season=', HTTP_HOST='testclub.ilovevoley.es'
        )
        self.assertEqual(self._titles(response), {'Actual', 'Pasado'})

    def test_galeria_individual_default_muestra_temporada_activa(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse('content:image_gallery_individual'), HTTP_HOST='testclub.ilovevoley.es'
        )
        self.assertEqual(self._titles(response), {'Actual'})

@override_settings(ALLOWED_HOSTS=['cluba.ilovevoley.es', 'clubb.ilovevoley.es', 'localhost'])
class ImageModerationTenantIsolationTests(TestCase):
    def setUp(self):
        from ilovevoley.users.models import Membership
        cache.clear()
        self.org_a = Organization.objects.create(slug='cluba', name='Club A', is_active=True)
        self.org_b = Organization.objects.create(slug='clubb', name='Club B', is_active=True)

        User = get_user_model()
        self.staff_a = User.objects.create_user(username='staff_a', password='pass', is_staff=True)
        Membership.objects.create(
            user=self.staff_a, organization=self.org_a, role='admin', is_approved=True
        )

        self.manager_a = User.objects.create_user(username='manager_a', password='pass')
        Membership.objects.create(
            user=self.manager_a, organization=self.org_a, role='manager', is_approved=True
        )

        self.member_a = User.objects.create_user(username='member_a', password='pass')
        Membership.objects.create(
            user=self.member_a, organization=self.org_a, role='member', is_approved=True
        )

        self.user_b = User.objects.create_user(username='user_b', password='pass')
        Membership.objects.create(
            user=self.user_b, organization=self.org_b, is_approved=True
        )

        self.image_a = Image.objects.create(
            image=SimpleUploadedFile('a.jpg', TINY_GIF, content_type='image/jpeg'),
            title='Imagen Club A',
            uploaded_by=self.staff_a,
            organization=self.org_a,
            status='pending',
        )
        self.image_b = Image.objects.create(
            image=SimpleUploadedFile('b.jpg', TINY_GIF, content_type='image/jpeg'),
            title='Imagen Club B',
            uploaded_by=self.user_b,
            organization=self.org_b,
            status='pending',
        )

    def test_image_moderation_view_only_lists_images_for_current_tenant(self):
        self.client.force_login(self.staff_a)
        url = reverse('content:image_moderation')
        response = self.client.get(url, HTTP_HOST='cluba.ilovevoley.es')
        self.assertEqual(response.status_code, 200)

        images = list(response.context['page_obj'].object_list)
        self.assertIn(self.image_a, images)
        self.assertNotIn(self.image_b, images)
        self.assertEqual(response.context['pending_count'], 1)

    def test_image_moderate_action_returns_404_for_other_tenant_image(self):
        self.client.force_login(self.staff_a)
        url = reverse('content:image_moderate_action', args=[self.image_b.id])
        response = self.client.get(url, HTTP_HOST='cluba.ilovevoley.es')
        self.assertEqual(response.status_code, 404)

        # POST también debe fallar con 404
        post_response = self.client.post(
            url, {'action': 'approve', 'moderation_notes': 'intento'}, HTTP_HOST='cluba.ilovevoley.es'
        )
        self.assertEqual(post_response.status_code, 404)
        self.image_b.refresh_from_db()
        self.assertEqual(self.image_b.status, 'pending')

    def test_image_moderate_action_allows_own_tenant_image(self):
        self.client.force_login(self.staff_a)
        url = reverse('content:image_moderate_action', args=[self.image_a.id])
        response = self.client.post(
            url, {'action': 'approve', 'moderation_notes': 'Aprobada OK'}, HTTP_HOST='cluba.ilovevoley.es'
        )
        self.assertRedirects(response, reverse('content:image_moderation'))
        self.image_a.refresh_from_db()
        self.assertEqual(self.image_a.status, 'approved')
        self.assertEqual(self.image_a.moderated_by, self.staff_a)
        self.assertEqual(self.image_a.moderation_notes, 'Aprobada OK')

    def test_image_moderate_bulk_only_modifies_own_tenant_images(self):
        self.client.force_login(self.staff_a)
        url = reverse('content:image_moderate_bulk')
        response = self.client.post(
            url,
            {
                'action': 'approve',
                'image_ids': [self.image_a.id, self.image_b.id],
                'notes': 'Bulk test',
            },
            HTTP_HOST='cluba.ilovevoley.es',
        )
        self.assertRedirects(response, reverse('content:image_moderation'))

        self.image_a.refresh_from_db()
        self.assertEqual(self.image_a.status, 'approved')

        # image_b debe permanecer intacta en pending
        self.image_b.refresh_from_db()
        self.assertEqual(self.image_b.status, 'pending')
        self.assertIsNone(self.image_b.moderated_by)

    def test_moderate_image_api_returns_404_for_other_tenant_image(self):
        self.client.force_login(self.staff_a)
        url = reverse('content:moderate_image_api', args=[self.image_b.id])
        response = self.client.post(url, {'action': 'approve'}, HTTP_HOST='cluba.ilovevoley.es')
        self.assertEqual(response.status_code, 404)

        self.image_b.refresh_from_db()
        self.assertEqual(self.image_b.status, 'pending')

    def test_moderate_image_api_allows_tenant_staff_or_manager(self):
        self.client.force_login(self.manager_a)
        url = reverse('content:moderate_image_api', args=[self.image_a.id])
        response = self.client.post(url, {'action': 'approve'}, HTTP_HOST='cluba.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])

        self.image_a.refresh_from_db()
        self.assertEqual(self.image_a.status, 'approved')
        self.assertEqual(self.image_a.moderated_by, self.manager_a)

    def test_moderate_image_api_denies_unauthorized_member(self):
        self.client.force_login(self.member_a)
        url = reverse('content:moderate_image_api', args=[self.image_a.id])
        response = self.client.post(url, {'action': 'approve'}, HTTP_HOST='cluba.ilovevoley.es')
        self.assertEqual(response.status_code, 403)

    def test_moderate_image_api_denies_global_staff_with_member_role(self):
        User = get_user_model()
        from ilovevoley.users.models import Membership
        staff_member = User.objects.create_user(username='staff_member', password='pass', is_staff=True)
        Membership.objects.create(
            user=staff_member, organization=self.org_a, role='member', is_approved=True
        )
        self.client.force_login(staff_member)
        url = reverse('content:moderate_image_api', args=[self.image_a.id])
        response = self.client.post(url, {'action': 'approve'}, HTTP_HOST='cluba.ilovevoley.es')
        self.assertEqual(response.status_code, 403)

    @override_settings(RATELIMIT_ENABLE=True, RATELIMIT_USE_CACHE='default')
    def test_moderate_image_api_rate_limiting(self):
        cache.clear()
        self.client.force_login(self.manager_a)
        url = reverse('content:moderate_image_api', args=[self.image_a.id])
        for _ in range(30):
            response = self.client.post(url, {'action': 'invalid'}, HTTP_HOST='cluba.ilovevoley.es')
            self.assertNotEqual(response.status_code, 429)

        blocked_response = self.client.post(url, {'action': 'invalid'}, HTTP_HOST='cluba.ilovevoley.es')
        self.assertEqual(blocked_response.status_code, 429)
        self.assertEqual(blocked_response['Content-Type'], 'application/json')


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'])
class ImageUploadSanitizationViewTests(TestCase):
    def setUp(self):
        import shutil
        import tempfile
        from ilovevoley.users.models import Membership

        cache.clear()
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        self.org = Organization.objects.create(slug='testclub', name='Test Club', is_active=True)
        User = get_user_model()
        self.user = User.objects.create_user(username='uploader', password='pass')
        Membership.objects.create(user=self.user, organization=self.org, is_approved=True)
        self.season = Season.objects.create(
            name='2026-27', start_year=2026, end_year=2027, is_current=True
        )

    def test_image_upload_view_sanitizes_exif_gps_and_assigns_descriptive_filename(self):
        from io import BytesIO
        from PIL import Image as PILImage
        from PIL.ExifTags import Base, GPS

        img = PILImage.new('RGB', (100, 100), color='red')
        exif = img.getexif()
        gps_ifd = exif.get_ifd(Base.GPSInfo)
        gps_ifd[GPS.GPSLatitude] = (40.4168, 0, 0)
        gps_ifd[GPS.GPSLongitude] = (3.7038, 0, 0)
        buf = BytesIO()
        img.save(buf, format='JPEG', exif=exif)
        buf.seek(0)

        uploaded = SimpleUploadedFile('foto_movil.jpg', buf.read(), content_type='image/jpeg')

        self.client.force_login(self.user)
        response = self.client.post(
            reverse('content:image_upload'),
            {
                'image': uploaded,
                'title': 'Foto con GPS subida',
                'image_type': 'training',
                'season': self.season.id,
            },
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 302)

        created = Image.objects.get(title='Foto con GPS subida')
        # Check that filename in storage uses descriptive slug
        filename = created.image.name.split('/')[-1]
        self.assertEqual(filename, 'foto-con-gps-subida-001.jpg')

        # Check that EXIF/GPS info is stripped
        created.image.open()
        saved_img = PILImage.open(created.image)
        self.assertEqual(dict(saved_img.getexif().get_ifd(Base.GPSInfo)), {})

    def test_image_bulk_upload_view_sanitizes_exif_and_assigns_descriptive_filename(self):
        from io import BytesIO
        from PIL import Image as PILImage
        from PIL.ExifTags import Base, GPS

        img = PILImage.new('RGB', (100, 100), color='blue')
        exif = img.getexif()
        gps_ifd = exif.get_ifd(Base.GPSInfo)
        gps_ifd[GPS.GPSLatitude] = (39.5696, 0, 0)
        gps_ifd[GPS.GPSLongitude] = (2.6502, 0, 0)
        buf = BytesIO()
        img.save(buf, format='JPEG', exif=exif)
        buf.seek(0)

        uploaded = SimpleUploadedFile('masiva.jpg', buf.read(), content_type='image/jpeg')

        self.client.force_login(self.user)
        response = self.client.post(
            reverse('content:image_bulk_upload'),
            {
                'images': [uploaded],
                'title_0': 'Foto masiva test',
                'image_type': 'training',
                'season': self.season.id,
            },
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 302)

        created = Image.objects.get(title='Foto masiva test')
        filename = created.image.name.split('/')[-1]
        self.assertEqual(filename, 'foto-masiva-test-001.jpg')

        created.image.open()
        saved_img = PILImage.open(created.image)
        self.assertEqual(dict(saved_img.getexif().get_ifd(Base.GPSInfo)), {})


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'])
class ImageDescriptiveNamingViewTests(TestCase):
    """Verifica el renombrado automático descriptivo en subidas individuales y masivas (#494).

    Justificación según docs/ai-guidelines/testing-guidelines.md:
    - Protege una regla de negocio del producto: formato descriptivo para partidos, álbumes y títulos compartidos.
    - Cubre flujos con efectos persistentes (títulos y rutas en storage asignados en views).
    """

    def setUp(self):
        import shutil
        import tempfile
        from datetime import datetime, timezone as dt_timezone
        from django.test import override_settings
        from ilovevoley.competitions.models import League, Match
        from ilovevoley.teams.models import Club, Team
        from ilovevoley.users.models import Membership

        cache.clear()
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        self.org = Organization.objects.create(slug='testclub', name='Test Club', is_active=True)
        User = get_user_model()
        self.user = User.objects.create_user(username='uploader', password='pass')
        Membership.objects.create(user=self.user, organization=self.org, is_approved=True)
        self.season = Season.objects.create(
            name='2026-27', start_year=2026, end_year=2027, is_current=True
        )
        self.club = Club.objects.create(official_name='CV Sant Josep', federation_id='SJ01')
        self.league = League.objects.create(name='1ª Balear', federation_id='L-BAL', season=self.season)
        self.home_team = Team.objects.create(name='CV Sant Josep', federation_id='T-SJ', club=self.club)
        self.away_team = Team.objects.create(name='CV Manacor', federation_id='T-MAN', club=self.club)
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.home_team,
            away_team=self.away_team,
            match_date=datetime(2026, 10, 15, 18, 0, tzinfo=dt_timezone.utc),
            federation_id='M-BAL-01',
        )

    def test_image_upload_with_match_generates_descriptive_title_and_filename(self):
        self.client.force_login(self.user)
        uploaded = SimpleUploadedFile('IMG_20261015.jpg', TINY_GIF, content_type='image/jpeg')
        response = self.client.post(
            reverse('content:image_upload'),
            {
                'image': uploaded,
                'title': '',
                'match': self.match.id,
                'image_type': 'match',
                'season': self.season.id,
            },
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 302)

        created = Image.objects.latest('id')
        self.assertEqual(created.title, 'CV Sant Josep vs CV Manacor - 15/10/2026 - 001')
        filename = created.image.name.split('/')[-1]
        self.assertEqual(filename, 'cv-sant-josep-vs-cv-manacor-2026-10-15-001.jpg')

    def test_image_bulk_upload_with_match_assigns_sequential_titles_and_paths(self):
        self.client.force_login(self.user)
        file1 = SimpleUploadedFile('DCIM001.jpg', TINY_GIF, content_type='image/jpeg')
        file2 = SimpleUploadedFile('DCIM002.jpg', TINY_GIF, content_type='image/jpeg')
        response = self.client.post(
            reverse('content:image_bulk_upload'),
            {
                'images': [file1, file2],
                'match': self.match.id,
                'title_0': '',
                'title_1': '',
                'image_type': 'match',
                'season': self.season.id,
            },
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 302)

        images = list(Image.objects.filter(match=self.match).order_by('id'))
        self.assertEqual(len(images), 2)
        self.assertEqual(images[0].title, 'CV Sant Josep vs CV Manacor - 15/10/2026 - 001')
        self.assertEqual(images[1].title, 'CV Sant Josep vs CV Manacor - 15/10/2026 - 002')
        self.assertTrue(images[0].image.name.endswith('cv-sant-josep-vs-cv-manacor-2026-10-15-001.jpg'))
        self.assertTrue(images[1].image.name.endswith('cv-sant-josep-vs-cv-manacor-2026-10-15-002.jpg'))

    def test_image_bulk_upload_with_shared_title_assigns_sequential_titles_and_paths(self):
        self.client.force_login(self.user)
        file1 = SimpleUploadedFile('IMG_01.jpg', TINY_GIF, content_type='image/jpeg')
        file2 = SimpleUploadedFile('IMG_02.jpg', TINY_GIF, content_type='image/jpeg')
        response = self.client.post(
            reverse('content:image_bulk_upload'),
            {
                'images': [file1, file2],
                'shared_title': 'Entrega de Trofeos',
                'title_0': '',
                'title_1': '',
                'image_type': 'celebration',
                'season': self.season.id,
            },
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 302)

        images = list(Image.objects.filter(image_type='celebration').order_by('id'))
        self.assertEqual(len(images), 2)
        self.assertEqual(images[0].title, 'Entrega de Trofeos - 001')
        self.assertEqual(images[1].title, 'Entrega de Trofeos - 002')
        self.assertTrue(images[0].image.name.endswith('entrega-de-trofeos-001.jpg'))
        self.assertTrue(images[1].image.name.endswith('entrega-de-trofeos-002.jpg'))


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'otherclub.ilovevoley.es', 'localhost'])
class GalleryQueryOptimizationTests(TestCase):
    """Stats, álbumes y tags de galería acotados al tenant y sin escanear todo en Python."""

    def setUp(self):
        from datetime import datetime, timezone as dt_timezone
        from ilovevoley.users.models import Membership
        from ilovevoley.competitions.models import League, Match
        from ilovevoley.teams.models import Team

        cache.clear()
        self.org = Organization.objects.create(slug='testclub', name='Test Club', is_active=True)
        self.other = Organization.objects.create(slug='otherclub', name='Other Club', is_active=True)
        User = get_user_model()
        self.user = User.objects.create_user(username='member', password='pass')
        Membership.objects.create(user=self.user, organization=self.org, is_approved=True)
        self.season = Season.objects.create(
            name='2026-27', start_year=2026, end_year=2027, is_current=True
        )
        self.league = League.objects.create(
            name='Liga Test', federation_id='LIG-G', season=self.season,
        )
        self.team_a = Team.objects.create(name='A', federation_id='G-A')
        self.team_b = Team.objects.create(name='B', federation_id='G-B')
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team_a,
            away_team=self.team_b,
            match_date=datetime(2026, 10, 1, 12, 0, tzinfo=dt_timezone.utc),
            federation_id='G-M1',
        )
        self.match2 = Match.objects.create(
            league=self.league,
            home_team=self.team_a,
            away_team=self.team_b,
            match_date=datetime(2026, 9, 1, 12, 0, tzinfo=dt_timezone.utc),
            federation_id='G-M2',
        )

    def _img(self, org, **kwargs):
        kwargs.setdefault('uploaded_by', self.user)
        kwargs.setdefault('status', 'approved')
        kwargs.setdefault('season', self.season)
        kwargs.setdefault('organization', org)
        kwargs.setdefault(
            'image',
            SimpleUploadedFile(f'{kwargs.get("title", "x")}.jpg', TINY_GIF, content_type='image/jpeg'),
        )
        return Image.objects.create(**kwargs)

    def test_gallery_stats_scoped_to_tenant(self):
        self._img(self.org, title='ours', status='approved')
        self._img(self.org, title='pending-ours', status='pending')
        self._img(self.other, title='theirs', status='approved')
        self._img(self.other, title='pending-theirs', status='pending')
        self._img(self.org, title='ours-match', match=self.match)

        self.client.force_login(self.user)
        response = self.client.get(
            reverse('content:image_gallery_individual') + '?season=',
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_images'], 2)
        self.assertEqual(response.context['pending_images'], 1)
        self.assertEqual(response.context['images_with_match'], 1)
        self.assertEqual(response.context['images_without_match'], 1)

    def test_albums_view_aggregates_match_images_and_paginates(self):
        import uuid
        for i in range(5):
            self._img(self.org, title=f'm1-{i}', match=self.match)
        for i in range(3):
            self._img(self.org, title=f'm2-{i}', match=self.match2)
        group_id = uuid.uuid4()
        for i in range(2):
            self._img(
                self.org, title=f'ag-{i}', album_group_id=group_id, album_name='Entrenamiento',
            )
        self._img(self.org, title='single')
        # Ruido de otra org: no debe aparecer ni inflar conteos
        self._img(self.other, title='other-match', match=self.match)

        self.client.force_login(self.user)
        response = self.client.get(
            reverse('content:image_gallery') + '?season=',
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        items = list(response.context['page_obj'].object_list)
        self.assertEqual(len(items), 4)  # 2 álbumes partido + 1 grupo + 1 single
        match_album = next(i for i in items if i['type'] == 'album' and i['match'].id == self.match.id)
        self.assertEqual(match_album['image_count'], 5)
        self.assertLessEqual(len(match_album['images']), 4)
        self.assertEqual(response.context['total_albums'], 3)
        self.assertEqual(response.context['total_single_images'], 1)
        self.assertEqual(response.context['total_images'], 11)  # solo org propia aprobadas

    def test_album_group_images_loads_lightbox_script_once(self):
        """base.html ya carga lightbox.js; el álbum no debe duplicarlo (#209)."""
        import uuid
        group_id = uuid.uuid4()
        self._img(self.org, title='ag-1', album_group_id=group_id, album_name='Entreno')
        self._img(self.org, title='ag-2', album_group_id=group_id, album_name='Entreno')

        self.client.force_login(self.user)
        response = self.client.get(
            reverse('content:album_group_images', args=[group_id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(_count_script(response.content, 'js/lightbox'), 1)

    def test_popular_tags_scoped_to_tenant_and_cached(self):
        self._img(self.org, title='t1', tags='saque, bloqueo', auto_tags=['voleibol'])
        self._img(self.org, title='t2', tags='saque', auto_tags=[])
        self._img(self.other, title='t3', tags='ajeno, saque', auto_tags=['otro'])

        self.client.force_login(self.user)
        response = self.client.get(
            reverse('content:image_gallery_individual') + '?season=',
            HTTP_HOST='testclub.ilovevoley.es',
        )
        tags = response.context['popular_tags']
        self.assertIn('saque', tags)
        self.assertIn('bloqueo', tags)
        self.assertIn('voleibol', tags)
        self.assertNotIn('ajeno', tags)
        self.assertNotIn('otro', tags)

        # Segunda petición no debe recalcular: cambiar datos no invalida hasta TTL
        self._img(self.org, title='t4', tags='nuevo-tag')
        response2 = self.client.get(
            reverse('content:image_gallery_individual') + '?season=',
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertNotIn('nuevo-tag', response2.context['popular_tags'])


class CoerceSetNumberTest(TestCase):
    """Normalización del número de set recibido por la vista (query/form)."""

    def test_invalid_values_become_none(self):
        for raw in (None, '', 'abc', '0', '-1'):
            self.assertIsNone(content_views._coerce_set_number(raw), raw)

    def test_valid_values_become_int(self):
        self.assertEqual(content_views._coerce_set_number('1'), 1)
        self.assertEqual(content_views._coerce_set_number('5'), 5)


@override_settings(ALLOWED_HOSTS=['cluba.ilovevoley.es', 'clubb.ilovevoley.es', 'localhost'])
class ImageFavoriteToggleTests(TestCase):
    """Toggle de favoritas: por usuario, solo fotos aprobadas y del propio tenant."""

    def setUp(self):
        from ilovevoley.users.models import Membership
        cache.clear()
        self.org_a = Organization.objects.create(slug='cluba', name='Club A', is_active=True)
        self.org_b = Organization.objects.create(slug='clubb', name='Club B', is_active=True)
        User = get_user_model()
        self.user_a = User.objects.create_user(username='member_a', password='pass')
        Membership.objects.create(user=self.user_a, organization=self.org_a, is_approved=True)
        self.user_a2 = User.objects.create_user(username='member_a2', password='pass')
        Membership.objects.create(user=self.user_a2, organization=self.org_a, is_approved=True)

        self.image_a = self._image(self.org_a, 'A')
        self.image_pending = self._image(self.org_a, 'P', status='pending')
        self.image_b = self._image(self.org_b, 'B')

    def _image(self, org, title, status='approved'):
        return Image.objects.create(
            image=SimpleUploadedFile(f'{title}.jpg', TINY_GIF, content_type='image/jpeg'),
            title=title,
            uploaded_by=self.user_a,
            organization=org,
            status=status,
        )

    def test_toggle_crea_y_elimina_la_favorita(self):
        self.client.force_login(self.user_a)
        url = reverse('content:toggle_image_favorite', args=[self.image_a.id])

        first = self.client.post(url, HTTP_HOST='cluba.ilovevoley.es')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), {'success': True, 'favorited': True, 'count': 1})
        self.assertEqual(self.image_a.favorites.count(), 1)

        second = self.client.post(url, HTTP_HOST='cluba.ilovevoley.es')
        self.assertEqual(second.json()['favorited'], False)
        self.assertEqual(second.json()['count'], 0)
        self.assertEqual(self.image_a.favorites.count(), 0)

    def test_contador_suma_favoritas_de_varios_usuarios(self):
        url = reverse('content:toggle_image_favorite', args=[self.image_a.id])
        self.client.force_login(self.user_a)
        self.client.post(url, HTTP_HOST='cluba.ilovevoley.es')
        self.client.force_login(self.user_a2)
        response = self.client.post(url, HTTP_HOST='cluba.ilovevoley.es')
        self.assertEqual(response.json()['count'], 2)

    def test_rechaza_foto_pendiente(self):
        self.client.force_login(self.user_a)
        url = reverse('content:toggle_image_favorite', args=[self.image_pending.id])
        response = self.client.post(url, HTTP_HOST='cluba.ilovevoley.es')
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.image_pending.favorites.exists())

    def test_rechaza_foto_de_otro_tenant(self):
        self.client.force_login(self.user_a)
        url = reverse('content:toggle_image_favorite', args=[self.image_b.id])
        response = self.client.post(url, HTTP_HOST='cluba.ilovevoley.es')
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.image_b.favorites.exists())

    def test_anonimo_redirige_a_login(self):
        url = reverse('content:toggle_image_favorite', args=[self.image_a.id])
        response = self.client.post(url, HTTP_HOST='cluba.ilovevoley.es')
        self.assertEqual(response.status_code, 302)

    def test_pagina_favoritas_solo_muestra_aprobadas_del_tenant(self):
        ImageFavorite.objects.create(user=self.user_a, image=self.image_a)
        ImageFavorite.objects.create(user=self.user_a, image=self.image_pending)
        ImageFavorite.objects.create(user=self.user_a, image=self.image_b)

        self.client.force_login(self.user_a)
        response = self.client.get(
            reverse('content:favorite_images'), HTTP_HOST='cluba.ilovevoley.es'
        )
        self.assertEqual(response.status_code, 200)
        ids = [img.id for img in response.context['page_obj'].object_list]
        self.assertEqual(ids, [self.image_a.id])
