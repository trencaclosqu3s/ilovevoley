from django.test import TestCase, RequestFactory, override_settings
from django.urls import reverse
from ilovevoley.core.views import service_worker


@override_settings(ALLOWED_HOSTS=['ilovevoley.es', 'santjosep.ilovevoley.es', 'localhost', 'testserver'])
class PWAServiceWorkerTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_service_worker_url_resolves(self):
        url = reverse('service_worker')
        self.assertEqual(url, '/sw.js')

        response = self.client.get('/sw.js')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/javascript; charset=utf-8')
        self.assertEqual(response['Service-Worker-Allowed'], '/')
        self.assertIn('no-cache', response['Cache-Control'])
        self.assertIn('no-store', response['Cache-Control'])
        self.assertIn('must-revalidate', response['Cache-Control'])

    def test_service_worker_headers(self):
        request = self.factory.get('/sw.js', HTTP_HOST='ilovevoley.es')
        response = service_worker(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'application/javascript; charset=utf-8')
        self.assertEqual(response.headers['Service-Worker-Allowed'], '/')
        self.assertIn('no-cache', response.headers['Cache-Control'])
        self.assertIn('no-store', response.headers['Cache-Control'])
        self.assertIn('must-revalidate', response.headers['Cache-Control'])

    def test_service_worker_content_specifications(self):
        request = self.factory.get('/sw.js', HTTP_HOST='ilovevoley.es')
        response = service_worker(request)
        content = response.content.decode('utf-8')

        # Cache name & precache
        self.assertIn('ilovevoley-pwa-v1', content)
        self.assertIn('/offline/', content)
        self.assertIn('/static/css/app.css', content)
        self.assertIn('/static/images/icons/icon-192.png', content)
        self.assertIn('/static/images/icons/icon-512.png', content)

        # Lifecycle events
        self.assertIn("'install'", content)
        self.assertIn("'activate'", content)
        self.assertIn("'fetch'", content)

        # Navigation and offline strategy
        self.assertIn('navigate', content)

        # Sensitive paths excluded from cache
        self.assertIn('/media/', content)
        self.assertIn('/protected-media/', content)
        self.assertIn('/accounts/', content)
        self.assertIn('/admin/', content)
