from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from ilovevoley.core.models import Organization
from ilovevoley.users.models import Membership

User = get_user_model()


@override_settings(ALLOWED_HOSTS=['ilovevoley.es', '.ilovevoley.es', 'localhost'])
class PWALandingMembershipsTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = User.objects.create_user(username='player', password='testpassword123')
        self.org1 = Organization.objects.create(slug='clubalpha', name='Club Alpha', is_active=True)
        self.org2 = Organization.objects.create(slug='clubbeta', name='Club Beta', is_active=True)
        self.org3 = Organization.objects.create(slug='clubgamma', name='Club Gamma', is_active=True)

    def test_single_approved_membership_redirects_to_tenant(self):
        Membership.objects.create(user=self.user, organization=self.org1, is_approved=True)
        self.client.login(username='player', password='testpassword123')

        response = self.client.get('/', HTTP_HOST='ilovevoley.es')
        self.assertEqual(response.status_code, 302)
        self.assertIn('clubalpha.', response.url)

    def test_multiple_approved_memberships_renders_landing_without_redirect(self):
        Membership.objects.create(user=self.user, organization=self.org1, is_approved=True)
        Membership.objects.create(user=self.user, organization=self.org2, is_approved=True)
        self.client.login(username='player', password='testpassword123')

        response = self.client.get('/', HTTP_HOST='ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertIn('user_organizations', response.context)
        self.assertEqual(len(response.context['user_organizations']), 2)
        self.assertIn(self.org1, response.context['user_organizations'])
        self.assertIn(self.org2, response.context['user_organizations'])
        self.assertIn('other_organizations', response.context)
        self.assertIn(self.org3, response.context['other_organizations'])
        self.assertNotIn(self.org1, response.context['other_organizations'])
        self.assertNotIn(self.org2, response.context['other_organizations'])
        self.assertContains(response, 'Tus clubes')

    def test_unapproved_membership_does_not_redirect(self):
        Membership.objects.create(user=self.user, organization=self.org1, is_approved=False)
        self.client.login(username='player', password='testpassword123')

        response = self.client.get('/', HTTP_HOST='ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context.get('user_organizations'), [])

    def test_inactive_organization_membership_does_not_redirect(self):
        inactive_org = Organization.objects.create(slug='inactive', name='Inactive Club', is_active=False)
        Membership.objects.create(user=self.user, organization=inactive_org, is_approved=True)
        self.client.login(username='player', password='testpassword123')

        response = self.client.get('/', HTTP_HOST='ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context.get('user_organizations'), [])

    def test_anonymous_user_renders_landing_without_redirect(self):
        response = self.client.get('/', HTTP_HOST='ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context.get('user_organizations'), [])
