import json
from django.test import TestCase, RequestFactory, override_settings
from ilovevoley.core.models import Organization
from ilovevoley.core.views import manifest_json


@override_settings(ALLOWED_HOSTS=['ilovevoley.es', '.ilovevoley.es', 'localhost', 'testserver'])
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

    def test_manifest_includes_scope_extensions_in_debug(self):
        Organization.objects.create(slug='soller', name='CV Soller', is_active=True)

        with self.settings(DEBUG=True):
            request = self.factory.get('/manifest.webmanifest', HTTP_HOST='santjosep.ilovevoley.es')
            request.tenant = self.org
            response = manifest_json(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode('utf-8'))
        self.assertIn('scope_extensions', data)
        origins = [item['origin'] for item in data['scope_extensions']]
        self.assertTrue(any('santjosep' in o for o in origins))
        self.assertTrue(any('soller' in o for o in origins))

    def test_manifest_includes_wildcard_scope_extensions_in_production(self):
        with self.settings(DEBUG=False, TENANT_BASE_DOMAIN='ilovevoley.es'):
            request = self.factory.get('/manifest.webmanifest', HTTP_HOST='santjosep.ilovevoley.es')
            request.tenant = self.org
            response = manifest_json(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode('utf-8'))
        self.assertIn('scope_extensions', data)
        origins = [item['origin'] for item in data['scope_extensions']]
        self.assertIn('https://ilovevoley.es', origins)
        self.assertIn('https://*.ilovevoley.es', origins)

    def test_web_app_origin_association(self):
        from ilovevoley.core.views import web_app_origin_association

        request = self.factory.get('/.well-known/web-app-origin-association', HTTP_HOST='ilovevoley.es')
        response = web_app_origin_association(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'application/json; charset=utf-8')
        data = json.loads(response.content.decode('utf-8'))
        self.assertIn('web_apps', data)
        self.assertEqual(data['web_apps'][0]['manifest'], '/manifest.webmanifest')
        origin_key = 'http://ilovevoley.es/'
        self.assertIn(origin_key, data)
        self.assertEqual(data[origin_key], {'scope': '/'})
