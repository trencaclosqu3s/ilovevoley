from django.test import TestCase, RequestFactory, override_settings
from django.contrib.auth import get_user_model
from django.core.cache import cache


class OrganizationModelTest(TestCase):
    def test_create_organization(self):
        from videosvoley.core.models import Organization
        org = Organization.objects.create(
            slug='testclub',
            name='Test Club',
            primary_color='#ff0000',
            club_team_names={'Senior': 'TEST CLUB'},
        )
        self.assertEqual(org.slug, 'testclub')
        self.assertEqual(org.club_team_names['Senior'], 'TEST CLUB')
        self.assertTrue(org.is_active)

    def test_slug_unique(self):
        from videosvoley.core.models import Organization
        from django.db import IntegrityError
        Organization.objects.create(slug='unique', name='A')
        with self.assertRaises(IntegrityError):
            Organization.objects.create(slug='unique', name='B')

    def test_instagram_handle(self):
        from videosvoley.core.models import Organization
        org = Organization.objects.create(
            slug='igclub',
            name='IG Club',
            instagram_url='https://www.instagram.com/clubvoleisantjosep/',
        )
        self.assertEqual(org.instagram_handle, '@clubvoleisantjosep')
        org.instagram_url = ''
        self.assertEqual(org.instagram_handle, '')


class MembershipModelTest(TestCase):
    def setUp(self):
        from videosvoley.core.models import Organization
        User = get_user_model()
        self.org = Organization.objects.create(slug='club1', name='Club 1')
        self.user = User.objects.create_user(username='testuser', password='pass')

    def test_create_membership(self):
        from videosvoley.users.models import Membership
        m = Membership.objects.create(
            user=self.user,
            organization=self.org,
            role='member',
            is_approved=False,
        )
        self.assertEqual(m.role, 'member')
        self.assertFalse(m.is_approved)

    def test_unique_user_organization(self):
        from videosvoley.users.models import Membership
        from django.db import IntegrityError
        Membership.objects.create(user=self.user, organization=self.org)
        with self.assertRaises(IntegrityError):
            Membership.objects.create(user=self.user, organization=self.org)


class TenantMiddlewareTest(TestCase):
    def setUp(self):
        from videosvoley.core.models import Organization
        cache.clear()
        self.org = Organization.objects.create(
            slug='testclub', name='Test Club', is_active=True
        )

    def test_middleware_sets_tenant_from_subdomain(self):
        from videosvoley.core.middleware import TenantMiddleware
        factory = RequestFactory()
        request = factory.get('/')
        request.META['HTTP_HOST'] = 'testclub.ilovevoley.es'

        middleware = TenantMiddleware(lambda r: type('R', (), {'status_code': 200})())
        middleware(request)

        self.assertEqual(request.tenant, self.org)

    def test_middleware_root_domain_sets_tenant_none(self):
        from videosvoley.core.middleware import TenantMiddleware

        factory = RequestFactory()
        request = factory.get('/')
        request.META['HTTP_HOST'] = 'ilovevoley.es'

        middleware = TenantMiddleware(lambda r: type('R', (), {'status_code': 200})())
        middleware(request)

        self.assertIsNone(request.tenant)

    def test_middleware_redirects_videos_without_tenant(self):
        from videosvoley.core.middleware import TenantMiddleware

        factory = RequestFactory()
        request = factory.get('/videos/')
        request.META['HTTP_HOST'] = 'ilovevoley.es'

        middleware = TenantMiddleware(lambda r: type('R', (), {'status_code': 200})())
        response = middleware(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')


@override_settings(ALLOWED_HOSTS=['ilovevoley.es', 'testclub.ilovevoley.es', 'localhost'])
class LandingViewTest(TestCase):
    def setUp(self):
        from videosvoley.core.models import Organization
        cache.clear()
        self.org = Organization.objects.create(
            slug='testclub', name='Test Club', is_active=True
        )

    def test_tenant_root_redirects_anonymous_to_login(self):
        response = self.client.get('/', HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)
        self.assertIn('next=/videos/', response.url)

    def test_root_domain_shows_landing_for_anonymous(self):
        response = self.client.get('/', HTTP_HOST='ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Selecciona tu club')

    def test_tenant_root_redirects_authenticated_to_videos(self):
        User = get_user_model()
        user = User.objects.create_user(username='member', password='pass')
        self.client.force_login(user)
        response = self.client.get('/', HTTP_HOST='testclub.ilovevoley.es')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/videos/')


class GetClubTeamFilterTest(TestCase):
    def test_returns_q_for_tenant_with_names(self):
        from videosvoley.core.models import Organization
        from videosvoley.core.mixins import get_club_team_filter
        org = Organization.objects.create(
            slug='testclub',
            name='Test',
            club_team_names={'Senior': 'TEST CLUB', 'Juvenil': 'TEST B'},
        )
        q = get_club_team_filter(org)
        self.assertIsNotNone(q)

    def test_falls_back_to_settings_when_no_tenant(self):
        from videosvoley.core.mixins import get_club_team_filter
        q = get_club_team_filter(None)
        self.assertIsNotNone(q)


class ClubTeamNamesTest(TestCase):
    def test_get_club_team_names_from_tenant(self):
        from videosvoley.core.models import Organization
        from videosvoley.core.mixins import get_club_team_names, get_primary_club_team_name
        org = Organization.objects.create(
            slug='club',
            name='Club',
            club_team_names={'Senior': 'SANT JOSEP', 'Juvenil': 'SANT JOSEP B'},
        )
        self.assertEqual(get_club_team_names(org), ['SANT JOSEP', 'SANT JOSEP B'])
        self.assertEqual(get_primary_club_team_name(org), 'SANT JOSEP')

    def test_get_club_team_name_filter_matches_all_names(self):
        from videosvoley.core.models import Organization
        from videosvoley.core.mixins import get_club_team_name_filter
        from videosvoley.videos.models import Team, Category

        org = Organization.objects.create(
            slug='club',
            name='Club',
            club_team_names={'Senior': 'SANT JOSEP', 'Juvenil': 'SANT JOSEP B'},
        )
        category = Category.objects.create(name='Senior', is_active=True)
        Team.objects.create(name='CV SANT JOSEP', category=category, federation_id='fed-1')
        Team.objects.create(name='CV RIVAL', category=category, federation_id='fed-2')

        teams = Team.objects.filter(get_club_team_name_filter(org))
        self.assertEqual(teams.count(), 1)


class TenantUtilsTest(TestCase):
    def setUp(self):
        from videosvoley.core.models import Organization
        cache.clear()
        self.org = Organization.objects.create(slug='club', name='Club')
        User = get_user_model()
        self.user = User.objects.create_user(username='member', password='pass')
        from videosvoley.users.models import Membership
        Membership.objects.create(user=self.user, organization=self.org, is_approved=False)

    def test_user_has_approved_membership(self):
        from videosvoley.core.tenant_utils import user_has_approved_membership, approve_user_membership
        self.assertFalse(user_has_approved_membership(self.user, self.org))
        approve_user_membership(self.user, self.org)
        self.assertTrue(user_has_approved_membership(self.user, self.org))

    @override_settings(TENANT_BASE_DOMAIN='localhost:8000', DEBUG=True)
    def test_build_tenant_url(self):
        from videosvoley.core.tenant_utils import build_tenant_url
        self.assertEqual(build_tenant_url('santjosep'), 'http://santjosep.localhost:8000/')

    def test_organization_cache(self):
        from videosvoley.core.tenant_utils import get_organization_by_slug, invalidate_organization_cache
        org = get_organization_by_slug('club')
        self.assertEqual(org, self.org)
        self.org.is_active = False
        self.org.save()
        invalidate_organization_cache('club')
        self.assertIsNone(get_organization_by_slug('club'))
