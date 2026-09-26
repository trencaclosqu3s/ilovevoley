from django.test import TestCase, RequestFactory
from django.core.cache import cache


class TenantMiddlewareTest(TestCase):
    def setUp(self):
        from ilovevoley.core.models import Organization
        cache.clear()
        self.org = Organization.objects.create(
            slug='testclub', name='Test Club', is_active=True
        )

    def test_middleware_sets_tenant_from_subdomain(self):
        from ilovevoley.core.middleware import TenantMiddleware
        factory = RequestFactory()
        request = factory.get('/')
        request.META['HTTP_HOST'] = 'testclub.ilovevoley.es'

        middleware = TenantMiddleware(lambda r: type('R', (), {'status_code': 200})())
        middleware(request)

        self.assertEqual(request.tenant, self.org)

    def test_middleware_root_domain_sets_tenant_none(self):
        from ilovevoley.core.middleware import TenantMiddleware

        factory = RequestFactory()
        request = factory.get('/')
        request.META['HTTP_HOST'] = 'ilovevoley.es'

        middleware = TenantMiddleware(lambda r: type('R', (), {'status_code': 200})())
        middleware(request)

        self.assertIsNone(request.tenant)

    def test_middleware_redirects_videos_without_tenant(self):
        from ilovevoley.core.middleware import TenantMiddleware

        factory = RequestFactory()
        request = factory.get('/videos/')
        request.META['HTTP_HOST'] = 'ilovevoley.es'

        middleware = TenantMiddleware(lambda r: type('R', (), {'status_code': 200})())
        response = middleware(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')

    def test_middleware_redirects_reserved_subdomain_www_to_root_domain(self):
        from ilovevoley.core.middleware import TenantMiddleware

        factory = RequestFactory()
        request = factory.get('/competitions/ligas/?season=2025-26', secure=True)
        request.META['HTTP_HOST'] = 'www.ilovevoley.es'

        middleware = TenantMiddleware(lambda r: type('R', (), {'status_code': 200})())
        response = middleware(request)

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, 'https://ilovevoley.es/competitions/ligas/?season=2025-26')

    def test_middleware_redirects_www_case_insensitive_and_preserves_port(self):
        from ilovevoley.core.middleware import TenantMiddleware

        factory = RequestFactory()
        request = factory.get('/videos/?filter=all')
        request.META['HTTP_HOST'] = 'WWW.ilovevoley.es:8000'

        middleware = TenantMiddleware(lambda r: type('R', (), {'status_code': 200})())
        response = middleware(request)

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, 'http://ilovevoley.es:8000/videos/?filter=all')

    def test_middleware_unknown_subdomain_returns_404(self):
        from ilovevoley.core.middleware import TenantMiddleware

        factory = RequestFactory()
        request = factory.get('/')
        request.META['HTTP_HOST'] = 'unknownclub.ilovevoley.es'

        middleware = TenantMiddleware(lambda r: type('R', (), {'status_code': 200})())
        response = middleware(request)

        self.assertEqual(response.status_code, 404)

