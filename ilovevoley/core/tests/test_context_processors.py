from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from ilovevoley.core.context_processors import tenant_context


class TenantContextTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _context(self, user=None, tenant=None):
        request = self.factory.get('/')
        request.user = user
        request.tenant = tenant
        return tenant_context(request)

    def test_superuser_without_tenant_keeps_manager_and_admin_flags(self):
        root = get_user_model().objects.create_superuser(username='root', password='pass')

        context = self._context(user=root, tenant=None)

        self.assertTrue(context['is_tenant_manager'])
        self.assertTrue(context['is_tenant_admin'])
        self.assertFalse(context['can_switch_club'])
        self.assertEqual(context['user_switch_clubs'], [])

    def test_user_with_multiple_memberships_gets_switch_clubs(self):
        from ilovevoley.core.models import Organization
        from ilovevoley.users.models import Membership

        user = get_user_model().objects.create_user(username='multiclub', password='pass')
        org1 = Organization.objects.create(slug='club1', name='Club Uno', primary_color='#111111', is_active=True)
        org2 = Organization.objects.create(slug='club2', name='Club Dos', primary_color='#222222', is_active=True)
        Membership.objects.create(user=user, organization=org1, is_approved=True)
        Membership.objects.create(user=user, organization=org2, is_approved=True)

        context = self._context(user=user, tenant=org1)

        self.assertTrue(context['can_switch_club'])
        switch_clubs = context['user_switch_clubs']
        self.assertEqual(len(switch_clubs), 2)

        current = next(c for c in switch_clubs if c['slug'] == 'club1')
        other = next(c for c in switch_clubs if c['slug'] == 'club2')

        self.assertTrue(current['is_current'])
        self.assertFalse(other['is_current'])
        self.assertEqual(current['name'], 'Club Uno')
        self.assertEqual(other['name'], 'Club Dos')
        self.assertIn('club2', other['url'])

    def test_user_with_single_membership_cannot_switch_club(self):
        from ilovevoley.core.models import Organization
        from ilovevoley.users.models import Membership

        user = get_user_model().objects.create_user(username='monoclub', password='pass')
        org1 = Organization.objects.create(slug='club1', name='Club Uno', is_active=True)
        Membership.objects.create(user=user, organization=org1, is_approved=True)

        context = self._context(user=user, tenant=org1)

        self.assertFalse(context['can_switch_club'])
        self.assertEqual(context['user_switch_clubs'], [])

