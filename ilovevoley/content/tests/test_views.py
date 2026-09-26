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
