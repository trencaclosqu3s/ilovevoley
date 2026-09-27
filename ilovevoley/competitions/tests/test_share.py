import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from ilovevoley.competitions.models import League, Match, MatchShareLink
from ilovevoley.competitions.share import (
    create_match_share_link,
    group_match_media,
    resolve_match_share_link,
    revoke_match_share_link,
)
from ilovevoley.content.models import Image
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.teams.models import Club, Team

TINY_GIF = (
    b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
    b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00'
    b'\x00\x02\x02D\x01\x00;'
)


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'])
class MatchShareLinkTest(TestCase):
    def setUp(self):
        cache.clear()
        self.org = Organization.objects.create(slug='testclub', name='Test Club', is_active=True)
        User = get_user_model()
        self.user = User.objects.create_user(username='manager', password='pass')
        self.category = Category.objects.create(name='Senior', is_active=True)
        self.club = Club.objects.create(official_name='Club Test', federation_id='CLUB-T')
        self.home = Team.objects.create(name='Test Senior', category=self.category, club=self.club, federation_id='T1')
        self.away = Team.objects.create(name='Rival Senior', category=self.category, federation_id='T2')
        self.league = League.objects.create(
            name='Liga Test', federation_id='L1',
            season=Season.objects.resolve('2026-2027'), is_active=True,
        )
        self.match = Match.objects.create(
            league=self.league, home_team=self.home, away_team=self.away,
            match_date=timezone.now(), status='finished', home_score=3, away_score=1,
        )

    def test_create_sets_expiry_and_token(self):
        link = create_match_share_link(self.match, self.org, self.user, hours=48)
        self.assertIsInstance(link.token, uuid.UUID)
        delta = link.expires_at - timezone.now()
        self.assertGreater(delta, timedelta(hours=47, minutes=55))
        self.assertLessEqual(delta, timedelta(hours=48))
        self.assertTrue(link.is_active)

    def test_create_clamps_hours_to_max(self):
        link = create_match_share_link(self.match, self.org, self.user, hours=10_000)
        self.assertLessEqual(link.expires_at - timezone.now(), timedelta(hours=720, minutes=1))

    def test_resolve_returns_active_link_and_none_when_expired(self):
        link = create_match_share_link(self.match, self.org, self.user, hours=48)
        self.assertEqual(resolve_match_share_link(link.token), link)

        MatchShareLink.objects.filter(pk=link.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertIsNone(resolve_match_share_link(link.token))

    def test_resolve_returns_none_when_revoked(self):
        link = create_match_share_link(self.match, self.org, self.user, hours=48)
        revoke_match_share_link(link)
        link.refresh_from_db()
        self.assertIsNotNone(link.revoked_at)
        self.assertIsNone(resolve_match_share_link(link.token))

    def test_resolve_unknown_token_returns_none(self):
        self.assertIsNone(resolve_match_share_link(uuid.uuid4()))

    def test_group_match_media_orders_sets_and_appends_ungrouped(self):
        groups = group_match_media(
            videos=[],
            images=[
                {'set_number': None, 'title': 'sin'},
                {'set_number': 2, 'title': 'dos'},
                {'set_number': 1, 'title': 'uno'},
            ],
            set_labels={1: 'Primer set'},
        )
        self.assertEqual([g['set_number'] for g in groups], [1, 2, None])
        self.assertEqual(groups[0]['label'], 'Primer set')
        self.assertEqual(groups[1]['label'], 'Set 2')
        self.assertEqual(groups[2]['label'], 'Sin set')
        self.assertEqual(groups[0]['images'], [{'set_number': 1, 'title': 'uno'}])


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'])
class MatchShareManagerViewsTest(TestCase):
    def setUp(self):
        from ilovevoley.users.models import Membership
        cache.clear()
        self.org = Organization.objects.create(slug='testclub', name='Test Club', is_active=True)
        User = get_user_model()
        self.manager = User.objects.create_user(username='manager', password='pass')
        Membership.objects.create(user=self.manager, organization=self.org, is_approved=True, role='manager')
        self.member = User.objects.create_user(username='member', password='pass')
        Membership.objects.create(user=self.member, organization=self.org, is_approved=True, role='member')
        self.category = Category.objects.create(name='Senior', is_active=True)
        self.club = Club.objects.create(official_name='Club Test', federation_id='CLUB-T')
        self.org.club = self.club
        self.org.save(update_fields=['club'])
        self.home = Team.objects.create(name='Test Senior', category=self.category, club=self.club, federation_id='T1')
        self.away = Team.objects.create(name='Rival Senior', category=self.category, federation_id='T2')
        self.league = League.objects.create(
            name='Liga Test', federation_id='L1',
            season=Season.objects.resolve('2026-2027'), is_active=True,
        )
        self.match = Match.objects.create(
            league=self.league, home_team=self.home, away_team=self.away,
            match_date=timezone.now(), status='finished', home_score=3, away_score=1,
        )

    def test_manager_creates_share_link(self):
        from django.urls import reverse
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('competitions:match_share_create', args=[self.match.id]),
            {'hours': '72'},
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 302)
        link = MatchShareLink.objects.get(match=self.match)
        self.assertEqual(link.organization, self.org)
        self.assertEqual(link.created_by, self.manager)

    def test_member_cannot_create_share_link(self):
        from django.urls import reverse
        self.client.force_login(self.member)
        response = self.client.post(
            reverse('competitions:match_share_create', args=[self.match.id]),
            {'hours': '48'},
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(MatchShareLink.objects.exists())

    def test_manager_revokes_share_link(self):
        from django.urls import reverse
        link = create_match_share_link(self.match, self.org, self.manager, hours=48)
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('competitions:match_share_revoke', args=[self.match.id, link.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 302)
        link.refresh_from_db()
        self.assertIsNotNone(link.revoked_at)

    def test_manager_does_not_see_other_tenant_links(self):
        from django.urls import reverse
        other_org = Organization.objects.create(slug='otherclub-x', name='Other X', is_active=True)
        foreign_link = create_match_share_link(self.match, other_org, self.manager, hours=48)
        self.client.force_login(self.manager)
        response = self.client.get(
            reverse('competitions:match_detail', args=[self.match.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(str(foreign_link.token), response.content.decode())

    def test_manager_revoke_foreign_link_returns_404(self):
        from django.urls import reverse
        other_org = Organization.objects.create(slug='otherclub-x', name='Other X', is_active=True)
        foreign_link = create_match_share_link(self.match, other_org, self.manager, hours=48)
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse('competitions:match_share_revoke', args=[self.match.id, foreign_link.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 404)
        foreign_link.refresh_from_db()
        self.assertIsNone(foreign_link.revoked_at)


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'])
class PublicTimelineViewTest(TestCase):
    def setUp(self):
        cache.clear()
        self.org = Organization.objects.create(slug='testclub', name='Test Club', is_active=True)
        User = get_user_model()
        self.user = User.objects.create_user(username='manager', password='pass')
        self.category = Category.objects.create(name='Senior', is_active=True)
        self.club = Club.objects.create(official_name='Club Test', federation_id='CLUB-T')
        self.home = Team.objects.create(name='Test Senior', category=self.category, club=self.club, federation_id='T1')
        self.away = Team.objects.create(name='Rival Senior', category=self.category, federation_id='T2')
        self.league = League.objects.create(
            name='Liga Test', federation_id='L1',
            season=Season.objects.resolve('2026-2027'), is_active=True,
        )
        self.match = Match.objects.create(
            league=self.league, home_team=self.home, away_team=self.away,
            match_date=timezone.now(), status='finished', home_score=3, away_score=1,
        )
        self.link = create_match_share_link(self.match, self.org, self.user, hours=48)

    def _image(self, title, organization):
        return Image.objects.create(
            image=SimpleUploadedFile('x.jpg', TINY_GIF, content_type='image/jpeg'),
            title=title, match=self.match, status='approved',
            uploaded_by=self.user, organization=organization, image_type='match',
        )

    def test_public_timeline_renders_without_login(self):
        from django.urls import reverse
        response = self.client.get(
            reverse('public:match_timeline', args=[self.link.token]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.home.name)
        self.assertEqual(response['Cache-Control'], 'private, no-store')

    def test_timeline_only_shows_media_of_the_link_organization(self):
        from django.urls import reverse
        self._image('Foto del club', self.org)
        other_org = Organization.objects.create(slug='otherclub', name='Other Club', is_active=True)
        self._image('Foto ajena', other_org)
        response = self.client.get(
            reverse('public:match_timeline', args=[self.link.token]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Foto del club')
        self.assertNotContains(response, 'Foto ajena')

    def test_public_timeline_404_for_revoked_link(self):
        from django.urls import reverse
        revoke_match_share_link(self.link)
        response = self.client.get(
            reverse('public:match_timeline', args=[self.link.token]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 404)

    def test_public_timeline_404_for_unknown_token(self):
        from django.urls import reverse
        response = self.client.get(
            reverse('public:match_timeline', args=[uuid.uuid4()]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 404)


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'], PROTECTED_MEDIA_USE_X_ACCEL=True)
class PublicMatchMediaViewTest(TestCase):
    def setUp(self):
        cache.clear()
        self.org = Organization.objects.create(slug='testclub', name='Test Club', is_active=True)
        self.other_org = Organization.objects.create(slug='otherclub', name='Other Club', is_active=True)
        User = get_user_model()
        self.user = User.objects.create_user(username='manager', password='pass')
        self.category = Category.objects.create(name='Senior', is_active=True)
        self.club = Club.objects.create(official_name='Club Test', federation_id='CLUB-T')
        self.home = Team.objects.create(name='Test Senior', category=self.category, club=self.club, federation_id='T1')
        self.away = Team.objects.create(name='Rival Senior', category=self.category, federation_id='T2')
        self.league = League.objects.create(
            name='Liga Test', federation_id='L1',
            season=Season.objects.resolve('2026-2027'), is_active=True,
        )
        self.match = Match.objects.create(
            league=self.league, home_team=self.home, away_team=self.away,
            match_date=timezone.now(), status='finished', home_score=3, away_score=1,
        )
        self.other_match = Match.objects.create(
            league=self.league, home_team=self.away, away_team=self.home,
            match_date=timezone.now(), status='finished',
        )
        self.link = create_match_share_link(self.match, self.org, self.user, hours=48)

    def _image(self, match, status='approved', organization=None):
        return Image.objects.create(
            image=SimpleUploadedFile('foto.gif', TINY_GIF, content_type='image/gif'),
            title='Foto', match=match, status=status,
            uploaded_by=self.user,
            organization=self.org if organization is None else organization,
            image_type='match',
        )

    def test_serves_approved_image_of_the_match(self):
        from django.urls import reverse
        image = self._image(self.match)
        response = self.client.get(
            reverse('public:match_media', args=[self.link.token, image.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['X-Accel-Redirect'].startswith('/protected-media/'))
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertEqual(response['X-Robots-Tag'], 'noindex, nofollow')

    def test_404_for_revoked_link(self):
        from django.urls import reverse
        image = self._image(self.match)
        revoke_match_share_link(self.link)
        response = self.client.get(
            reverse('public:match_media', args=[self.link.token, image.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 404)

    def test_404_for_expired_link(self):
        from django.urls import reverse
        image = self._image(self.match)
        MatchShareLink.objects.filter(pk=self.link.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        response = self.client.get(
            reverse('public:match_media', args=[self.link.token, image.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 404)

    def test_404_for_unknown_token(self):
        from django.urls import reverse
        image = self._image(self.match)
        response = self.client.get(
            reverse('public:match_media', args=[uuid.uuid4(), image.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 404)

    def test_404_for_image_of_another_match(self):
        from django.urls import reverse
        image = self._image(self.other_match)
        response = self.client.get(
            reverse('public:match_media', args=[self.link.token, image.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 404)

    def test_404_for_non_approved_image(self):
        from django.urls import reverse
        image = self._image(self.match, status='pending')
        response = self.client.get(
            reverse('public:match_media', args=[self.link.token, image.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 404)

    def test_404_for_image_of_a_different_organization(self):
        from django.urls import reverse
        image = self._image(self.match, organization=self.other_org)
        response = self.client.get(
            reverse('public:match_media', args=[self.link.token, image.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 404)

    def test_404_for_image_without_organization(self):
        from django.urls import reverse
        image = self._image(self.match)
        image.organization = None
        image.save(update_fields=['organization'])
        response = self.client.get(
            reverse('public:match_media', args=[self.link.token, image.id]),
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 404)

    def test_media_variants_resolve_to_expected_field(self):
        from django.urls import reverse
        image = self._image(self.match)
        image.thumbnail_small.name = 'images/small.gif'
        image.thumbnail_large.name = 'images/large.gif'
        image.save(update_fields=['thumbnail_small', 'thumbnail_large'])
        url = reverse('public:match_media', args=[self.link.token, image.id])

        thumb = self.client.get(url, HTTP_HOST='testclub.ilovevoley.es')
        large = self.client.get(url, {'v': 'large'}, HTTP_HOST='testclub.ilovevoley.es')
        orig = self.client.get(url, {'v': 'orig'}, HTTP_HOST='testclub.ilovevoley.es')
        unknown = self.client.get(url, {'v': 'unknown'}, HTTP_HOST='testclub.ilovevoley.es')

        self.assertEqual(
            [thumb.status_code, large.status_code, orig.status_code, unknown.status_code],
            [200, 200, 200, 200],
        )
        self.assertTrue(thumb['X-Accel-Redirect'].endswith('images/small.gif'))
        self.assertTrue(large['X-Accel-Redirect'].endswith('images/large.gif'))
        self.assertTrue(orig['X-Accel-Redirect'].endswith(image.image.name))
        self.assertNotEqual(orig['X-Accel-Redirect'], thumb['X-Accel-Redirect'])
        self.assertEqual(unknown['X-Accel-Redirect'], thumb['X-Accel-Redirect'])


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'], ACTA_ALLOWED_HOSTS=['fed.example.com'])
class MatchSetLabelsTest(TestCase):
    def setUp(self):
        cache.clear()
        self.org = Organization.objects.create(slug='testclub', name='Test Club', is_active=True)
        self.category = Category.objects.create(name='Senior', is_active=True)
        self.league = League.objects.create(
            name='Liga Test', federation_id='L1',
            season=Season.objects.resolve('2026-2027'), is_active=True,
        )
        self.match = Match.objects.create(
            league=self.league, match_date=timezone.now(), status='finished',
            acta_html='https://fed.example.com/acta/1',
        )

    def test_returns_empty_without_acta(self):
        from ilovevoley.competitions.share import get_match_set_labels
        self.match.acta_html = ''
        self.assertEqual(get_match_set_labels(self.match), {})

    @patch('ilovevoley.competitions.share.safe_get')
    @patch('ilovevoley.competitions.share.parse_acta_lineup')
    def test_returns_labels_from_acta(self, mock_parse, mock_get):
        from ilovevoley.competitions.share import get_match_set_labels
        mock_parse.return_value = {'sets': [{'title': 'Set 1'}, {'title': 'Set 2'}]}
        labels = get_match_set_labels(self.match)
        self.assertEqual(labels, {1: 'Set 1', 2: 'Set 2'})
        mock_get.assert_called_once()

    @patch('ilovevoley.competitions.share.safe_get', side_effect=Exception('boom'))
    def test_returns_empty_on_fetch_error(self, mock_get):
        from ilovevoley.competitions.share import get_match_set_labels
        self.assertEqual(get_match_set_labels(self.match), {})

    @patch('ilovevoley.competitions.share.safe_get')
    @patch('ilovevoley.competitions.share.parse_acta_lineup')
    def test_returns_empty_when_parse_result_is_not_a_dict(self, mock_parse, mock_get):
        from ilovevoley.competitions.share import get_match_set_labels
        mock_parse.return_value = None
        self.assertEqual(get_match_set_labels(self.match), {})
