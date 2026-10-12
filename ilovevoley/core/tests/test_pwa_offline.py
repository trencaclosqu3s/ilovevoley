from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory, override_settings
from ilovevoley.core.views import offline_view


@override_settings(ALLOWED_HOSTS=['ilovevoley.es', 'santjosep.ilovevoley.es', 'localhost', 'testserver'])
class PWAOfflineTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_offline_page_exposes_reload_action_wired_by_js(self):
        """El fallback offline se sirve desde caché sin red; su botón
        «Reintentar» solo funciona si ``data-action="reload"`` coincide con el
        handler que expone ``csp_actions.js``."""
        js_path = Path(settings.BASE_DIR, 'ilovevoley', 'static', 'js', 'csp_actions.js')
        js = js_path.read_text(encoding='utf-8')
        self.assertIn('"reload"', js, 'csp_actions.js no implementa la acción reload')

        request = self.factory.get('/offline/', HTTP_HOST='ilovevoley.es')
        request.tenant = None
        response = offline_view(request)

        content = response.content.decode('utf-8')
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
