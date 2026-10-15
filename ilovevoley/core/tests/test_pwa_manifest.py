import json
from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, RequestFactory, override_settings
from ilovevoley.core.models import Organization
from ilovevoley.core.views import manifest_json


@override_settings(ALLOWED_HOSTS=['ilovevoley.es', '.ilovevoley.es', 'localhost', 'testserver'])
class PWAManifestTest(TestCase):
    def setUp(self):
        cache.clear()
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
        self.assertEqual(data['theme_color'], '#01696f')
        self.assertEqual(data['background_color'], '#ffffff')
        self.assertTrue(len(data['icons']) >= 3)

    def test_manifest_declares_share_target(self):
        """share_target es el contrato de plataforma: sin él la app no aparece en la
        hoja de compartir y no hay error visible. Cubre POST+multipart+nombre de campo
        exactos que validan Chrome/Edge al registrar el target (guidelines: regla de
        negocio + camino crítico detectable solo en producción)."""
        request = self.factory.get('/manifest.webmanifest', HTTP_HOST='ilovevoley.es')
        request.tenant = None
        data = json.loads(manifest_json(request).content.decode('utf-8'))

        share_target = data['share_target']
        self.assertEqual(share_target['action'], '/content/imagenes/compartida/')
        self.assertEqual(share_target['method'], 'POST')
        self.assertEqual(share_target['enctype'], 'multipart/form-data')
        files = share_target['params']['files']
        self.assertEqual(files[0]['name'], 'image')
        self.assertTrue(files[0]['multiple'])
        self.assertIn('image/jpeg', files[0]['accept'])
        self.assertEqual(share_target['params']['title'], 'title')
        self.assertEqual(share_target['params']['text'], 'text')

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
        self.assertEqual(data['theme_color'], '#01696f')

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

        with self.settings(TENANT_BASE_DOMAIN='ilovevoley.es'):
            request = self.factory.get('/.well-known/web-app-origin-association', HTTP_HOST='santjosep.ilovevoley.es')
            response = web_app_origin_association(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'application/json; charset=utf-8')
        data = json.loads(response.content.decode('utf-8'))
        self.assertIn('web_apps', data)
        self.assertEqual(data['web_apps'][0]['manifest'], '/manifest.webmanifest')
        base_domain = 'ilovevoley.es'
        protocol = 'https' if not settings.DEBUG else 'http'
        self.assertIn(f'{protocol}://{base_domain}/', data)
        self.assertIn(f'{protocol}://santjosep.{base_domain}/', data)
        self.assertEqual(data[f'{protocol}://santjosep.{base_domain}/'], {'scope': '/'})

    def test_web_app_origin_association_invalidates_cache_on_organization_change(self):
        from ilovevoley.core.views import web_app_origin_association

        with self.settings(TENANT_BASE_DOMAIN='ilovevoley.es'):
            request = self.factory.get('/.well-known/web-app-origin-association', HTTP_HOST='santjosep.ilovevoley.es')
            response1 = web_app_origin_association(request)
            data1 = json.loads(response1.content.decode('utf-8'))
            protocol = 'https' if not settings.DEBUG else 'http'
            self.assertNotIn(f'{protocol}://manacor.ilovevoley.es/', data1)

            # Creating a new active organization triggers cache invalidation via post_save signal
            Organization.objects.create(slug='manacor', name='CV Manacor', is_active=True)

            response2 = web_app_origin_association(request)
            data2 = json.loads(response2.content.decode('utf-8'))
            self.assertIn(f'{protocol}://manacor.ilovevoley.es/', data2)

    def test_manifest_includes_shortcuts(self):
        """Verifica que el manifiesto expone al menos 3 shortcuts con estructura W3C estándar (#523)."""
        request = self.factory.get('/manifest.webmanifest', HTTP_HOST='ilovevoley.es')
        request.tenant = None
        response = manifest_json(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode('utf-8'))
        self.assertIn('shortcuts', data)
        shortcuts = data['shortcuts']
        self.assertGreaterEqual(len(shortcuts), 3)

        urls = [s.get('url') for s in shortcuts]
        # #522: el shortcut «Hoy / este finde» apunta a la pantalla propia /finde/.
        self.assertIn('/finde/', urls)
        self.assertIn('/content/imagenes/', urls)
        self.assertIn('/profile/?tab=avisos#activar', urls)

        for sc in shortcuts:
            self.assertTrue(sc.get('name'))
            self.assertTrue(sc.get('short_name'))
            self.assertTrue(sc.get('url', '').startswith('/'))
            self.assertTrue(len(sc.get('icons', [])) >= 1)
            for icon in sc['icons']:
                self.assertTrue(icon.get('src'))
                self.assertEqual(icon.get('sizes'), '192x192')
                self.assertEqual(icon.get('type'), 'image/png')

    def test_manifest_shortcuts_on_tenant_domain(self):
        """Verifica que los shortcuts se exponen también en subdominios de tenant (#523)."""
        request = self.factory.get('/manifest.webmanifest', HTTP_HOST='santjosep.ilovevoley.es')
        request.tenant = self.org
        response = manifest_json(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode('utf-8'))
        self.assertIn('shortcuts', data)
        shortcuts = data['shortcuts']
        self.assertGreaterEqual(len(shortcuts), 3)

        urls = [s.get('url') for s in shortcuts]
        # #522: el shortcut «Hoy / este finde» apunta a la pantalla propia /finde/.
        self.assertIn('/finde/', urls)
        self.assertIn('/content/imagenes/', urls)
        self.assertIn('/profile/?tab=avisos#activar', urls)

        for sc in shortcuts:
            for icon in sc['icons']:
                self.assertIn('shortcut-', icon['src'])
