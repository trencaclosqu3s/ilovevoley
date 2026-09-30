from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory, override_settings
from django.urls import reverse
from ilovevoley.core.models import Organization
from ilovevoley.core.views import offline_view


@override_settings(ALLOWED_HOSTS=['ilovevoley.es', 'santjosep.ilovevoley.es', 'localhost', 'testserver'])
class PWAOfflineTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.org, _ = Organization.objects.get_or_create(
            slug='santjosep',
            defaults={
                'name': 'CV Sant Josep',
                'primary_color': '#9B7FBF',
                'is_active': True,
            },
        )

    def test_offline_url_resolves(self):
        url = reverse('offline_fallback')
        self.assertEqual(url, '/offline/')

    def test_offline_page_renders_cleanly(self):
        request = self.factory.get('/offline/', HTTP_HOST='ilovevoley.es')
        request.tenant = None
        response = offline_view(request)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('Sin conexión', content)
        self.assertIn('Reintentar', content)
        self.assertIn('logo_app.png', content)
        self.assertIn('data-action="reload"', content)

    def test_offline_page_with_tenant(self):
        request = self.factory.get('/offline/', HTTP_HOST='santjosep.ilovevoley.es')
        request.tenant = self.org
        response = offline_view(request)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('Sin conexión', content)
        self.assertIn('Reintentar', content)

    def test_offline_page_has_no_sensitive_data_even_if_authenticated(self):
        User = get_user_model()
        user = User.objects.create_user(username='offline_tester', email='offline@example.com', password='password123')
        self.client.force_login(user)

        response = self.client.get('/offline/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertNotIn('csrfmiddlewaretoken', content)
        self.assertNotIn('sessionid', content)
        self.assertNotIn('offline_tester', content)
        self.assertNotIn('offline@example.com', content)
