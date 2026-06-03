from django.test import TestCase


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


class MembershipModelTest(TestCase):
    def setUp(self):
        from videosvoley.core.models import Organization
        from django.contrib.auth import get_user_model
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
        self.org = Organization.objects.create(
            slug='testclub', name='Test Club', is_active=True
        )

    def test_middleware_sets_tenant_from_subdomain(self):
        from django.test import RequestFactory
        from videosvoley.core.middleware import TenantMiddleware
        factory = RequestFactory(SERVER_NAME='testclub.ilovevoley.es')
        request = factory.get('/')
        request.META['HTTP_HOST'] = 'testclub.ilovevoley.es'

        middleware = TenantMiddleware(lambda r: type('R', (), {'status_code': 200})())
        middleware(request)

        self.assertEqual(request.tenant, self.org)

    def test_middleware_root_domain_sets_tenant_none(self):
        from django.test import RequestFactory
        from videosvoley.core.middleware import TenantMiddleware

        factory = RequestFactory()
        request = factory.get('/')
        request.META['HTTP_HOST'] = 'ilovevoley.es'

        middleware = TenantMiddleware(lambda r: type('R', (), {'status_code': 200})())
        middleware(request)

        self.assertIsNone(request.tenant)


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
        from django.db.models import Q
        q = get_club_team_filter(None)
        self.assertIsNotNone(q)
