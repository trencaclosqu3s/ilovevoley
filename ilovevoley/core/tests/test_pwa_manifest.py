import json
from django.test import TestCase, RequestFactory
from django.urls import reverse
from ilovevoley.core.models import Organization
from ilovevoley.core.views import manifest_json


class PWAManifestTest(TestCase):
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
        self.org.primary_color = '#9B7FBF'
        self.org.save()

    def test_manifest_url_resolves(self):
        url = reverse('manifest_json')
        self.assertEqual(url, '/manifest.webmanifest')

    def test_manifest_apex_domain(self):
        request = self.factory.get('/manifest.webmanifest', HTTP_HOST='ilovevoley.es')
        request.tenant = None
        response = manifest_json(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'application/manifest+json; charset=utf-8')
        self.assertEqual(response.headers['Cache-Control'], 'public, max-age=3600')
        self.assertEqual(response.headers['Vary'], 'Host')
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')

        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(data['id'], '/')
        self.assertEqual(data['name'], 'I Love Voley')
        self.assertEqual(data['short_name'], 'ILoveVoley')
        self.assertEqual(data['lang'], 'es')
        self.assertEqual(data['dir'], 'ltr')
        self.assertEqual(data['start_url'], '/')
        self.assertEqual(data['scope'], '/')
        self.assertEqual(data['display'], 'standalone')
        self.assertEqual(data['theme_color'], '#9B7FBF')
        self.assertEqual(data['background_color'], '#ffffff')
        self.assertTrue(len(data['icons']) >= 3)

    def test_manifest_tenant_domain_uses_tenant_color(self):
        self.org.primary_color = '#FF5500'
        self.org.save()

        request = self.factory.get('/manifest.webmanifest', HTTP_HOST='santjosep.ilovevoley.es')
        request.tenant = self.org
        response = manifest_json(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(data['name'], 'I Love Voley')
        self.assertEqual(data['theme_color'], '#FF5500')

    def test_manifest_tenant_without_color_uses_default(self):
        request = self.factory.get('/manifest.webmanifest', HTTP_HOST='santjosep.ilovevoley.es')
        self.org.primary_color = None
        request.tenant = self.org
        response = manifest_json(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(data['theme_color'], '#9B7FBF')
