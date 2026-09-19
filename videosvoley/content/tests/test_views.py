from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.cache import cache

from videosvoley.core.models import Organization
from videosvoley.content import forms as content_forms
from videosvoley.content import views as content_views
from videosvoley.videos.forms import content as videos_forms_content
from videosvoley.videos.views import content as videos_views_content
from videosvoley.videos.views import moderation as videos_views_moderation


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
