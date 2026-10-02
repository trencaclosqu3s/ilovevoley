from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory, override_settings
from django.urls import reverse
from ilovevoley.core.views import offline_view


@override_settings(ALLOWED_HOSTS=['ilovevoley.es', 'santjosep.ilovevoley.es', 'localhost', 'testserver'])
class PWAOfflineTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_offline_url_resolves(self):
        url = reverse('offline_fallback')
        self.assertEqual(url, '/offline/')

    def test_offline_page_renders_cleanly(self):
        """El fallback offline debe precachear el logo y exponer la acción que
        ``csp_actions.js`` engancha para recargar (``data-action="reload"``),
        que es el contrato funcional de la página servida sin red."""
        request = self.factory.get('/offline/', HTTP_HOST='ilovevoley.es')
        request.tenant = None
        response = offline_view(request)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('images/logo_app', content)
        self.assertIn('data-action="reload"', content)

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
