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
        self.assertIn('name="theme-color"', content)
        self.assertIn('apple-touch-icon-180.png', content)
        self.assertIn('apple-mobile-web-app-capable', content)
        self.assertIn("navigator.serviceWorker.register('/sw.js')", content)

    def test_base_auth_template_contains_pwa_metas(self):
        response = self.client.get('/accounts/login/', HTTP_HOST='ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        self.assertIn('rel="manifest"', content)
        self.assertIn('name="theme-color"', content)
        self.assertIn('apple-touch-icon-180.png', content)
        self.assertIn('apple-mobile-web-app-capable', content)
        self.assertIn("navigator.serviceWorker.register('/sw.js')", content)
