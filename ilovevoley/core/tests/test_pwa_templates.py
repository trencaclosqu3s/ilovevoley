from django.test import Client, TestCase, override_settings


@override_settings(ALLOWED_HOSTS=['ilovevoley.es', '.ilovevoley.es', 'localhost', 'testserver'])
class PWATemplatesTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_base_template_contains_pwa_metas_and_script(self):
        response = self.client.get('/', HTTP_HOST='ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        self.assertIn('rel="manifest"', content)
        self.assertIn("navigator.serviceWorker.register('/sw.js')", content)

    def test_base_auth_template_contains_pwa_metas(self):
        response = self.client.get('/accounts/login/', HTTP_HOST='ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        self.assertIn('rel="manifest"', content)
        self.assertIn("navigator.serviceWorker.register('/sw.js')", content)

    def test_navbar_renders_in_app_club_switcher_when_multi_membership(self):
        from django.contrib.auth import get_user_model
        from ilovevoley.core.models import Organization
        from ilovevoley.users.models import Membership

        user = get_user_model().objects.create_user(username='switcher', password='testpassword123')
        org1 = Organization.objects.create(slug='clubalpha', name='Club Alpha', is_active=True)
        org2 = Organization.objects.create(slug='clubbeta', name='Club Beta', is_active=True)
        Membership.objects.create(user=user, organization=org1, is_approved=True)
        Membership.objects.create(user=user, organization=org2, is_approved=True)

        self.client.login(username='switcher', password='testpassword123')
        response = self.client.get('/profile/', HTTP_HOST='clubalpha.ilovevoley.es')

        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        self.assertIn('data-dropdown="club-switcher"', content)
        self.assertIn('data-dropdown-menu="club-switcher"', content)
        self.assertIn('Club Alpha', content)
        self.assertIn('Club Beta', content)
        self.assertIn('Actual', content)
