from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from videosvoley.core.models import Organization, Season
from videosvoley.content import forms as content_forms
from videosvoley.content import views as content_views
from videosvoley.content.models import Image, Video
from videosvoley.videos.forms import content as videos_forms_content
from videosvoley.videos.views import content as videos_views_content
from videosvoley.videos.views import moderation as videos_views_moderation

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
        from videosvoley.users.models import Membership
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
        from videosvoley.users.models import Membership
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

