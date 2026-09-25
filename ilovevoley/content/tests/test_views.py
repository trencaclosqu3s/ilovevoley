from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from ilovevoley.core.models import Organization, Season
from ilovevoley.content import forms as content_forms
from ilovevoley.content import views as content_views
from ilovevoley.content.models import Image, Video
from ilovevoley.videos.forms import content as videos_forms_content
from ilovevoley.videos.views import content as videos_views_content
from ilovevoley.videos.views import moderation as videos_views_moderation

TINY_GIF = (
    b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
    b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00'
    b'\x00\x02\x02D\x01\x00;'
)


class ContentReExportCompatibilityTest(TestCase):
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

    def test_content_video_list_url_resolves_and_renders(self):
        self.client.force_login(self.user)
        url = reverse('content:video_list')
        self.assertEqual(url, '/content/')
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'content/video_list.html')

    def test_backwards_compatible_videos_video_list_url_renders(self):
        self.client.force_login(self.user)
        url = reverse('videos:video_list')
        self.assertEqual(url, '/videos/')
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'content/video_list.html')

    def test_content_image_gallery_url_resolves_and_renders(self):
        self.client.force_login(self.user)
        url = reverse('content:image_gallery')
        self.assertEqual(url, '/content/imagenes/')
        response = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'content/image_gallery.html')

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

    def test_video_list_id_de_temporada_invalido_cae_a_la_activa(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse('content:video_list') + '?season=999999',
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(self._titles(response), {'Actual'})

    def test_video_list_temporada_no_numerica_no_rompe(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse('content:video_list') + '?season=abc',
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._titles(response), {'Actual'})

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
            user=self.staff_a, organization=self.org_a, is_approved=True
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


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'])
class ImageUploadSanitizationViewTests(TestCase):
    def setUp(self):
        from ilovevoley.users.models import Membership
        cache.clear()
        self.org = Organization.objects.create(slug='testclub', name='Test Club', is_active=True)
        User = get_user_model()
        self.user = User.objects.create_user(username='uploader', password='pass')
        Membership.objects.create(user=self.user, organization=self.org, is_approved=True)
        self.season = Season.objects.create(
            name='2026-27', start_year=2026, end_year=2027, is_current=True
        )

    def test_image_upload_view_sanitizes_exif_gps_and_assigns_uuid(self):
        import uuid
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
        # Check that filename in storage uses UUID
        filename = created.image.name.split('/')[-1]
        base_name = filename.split('.')[0]
        self.assertEqual(uuid.UUID(base_name).hex, base_name)

        # Check that EXIF/GPS info is stripped
        created.image.open()
        saved_img = PILImage.open(created.image)
        self.assertEqual(dict(saved_img.getexif().get_ifd(Base.GPSInfo)), {})



