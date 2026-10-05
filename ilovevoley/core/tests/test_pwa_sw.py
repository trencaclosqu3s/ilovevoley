import re

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

    def test_service_worker_content_specifications(self):
        request = self.factory.get('/sw.js', HTTP_HOST='ilovevoley.es')
        response = service_worker(request)
        content = response.content.decode('utf-8')

        self.assertIn('ilovevoley-pwa-v2', content)

        precache_block = re.search(r'PRECACHE_URLS\s*=\s*\[(.*?)\]', content, re.S)
        self.assertIsNotNone(precache_block, 'el SW debe declarar PRECACHE_URLS')
        precached = re.findall(r"['\"]([^'\"]+)['\"]", precache_block.group(1))

        for asset in (
            '/offline/',
            '/static/css/app.css',
            '/static/images/icons/icon-192.png',
            '/static/images/icons/icon-512.png',
        ):
            self.assertIn(asset, precached)

        # Rutas sensibles: ni precacheadas ni cacheables en runtime. La
        # comprobación es que no aparezcan en PRECACHE_URLS y que el handler de
        # ``fetch`` las descarte antes de tocar la caché.
        for prefix in ('/media/', '/protected-media/', '/accounts/', '/admin/'):
            self.assertFalse(
                any(url.startswith(prefix) for url in precached),
                f'{prefix} no debe aparecer en PRECACHE_URLS',
            )
            self.assertIn(f"pathname.startsWith('{prefix}')", content)

