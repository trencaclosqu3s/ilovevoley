from django.test import TestCase, RequestFactory
from django.core.cache import cache


class TenantMiddlewareTest(TestCase):
    def setUp(self):
        from videosvoley.core.models import Organization
        cache.clear()
        self.org = Organization.objects.create(
            slug='testclub', name='Test Club', is_active=True
        )

    def test_middleware_sets_tenant_from_subdomain(self):
        from videosvoley.core.middleware import TenantMiddleware
        factory = RequestFactory()
        request = factory.get('/')
        request.META['HTTP_HOST'] = 'testclub.ilovevoley.es'

        middleware = TenantMiddleware(lambda r: type('R', (), {'status_code': 200})())
        middleware(request)

        self.assertEqual(request.tenant, self.org)

    def test_middleware_root_domain_sets_tenant_none(self):
        from videosvoley.core.middleware import TenantMiddleware

        factory = RequestFactory()
        request = factory.get('/')
        request.META['HTTP_HOST'] = 'ilovevoley.es'

        middleware = TenantMiddleware(lambda r: type('R', (), {'status_code': 200})())
        middleware(request)

        self.assertIsNone(request.tenant)

    def test_middleware_redirects_videos_without_tenant(self):
        from videosvoley.core.middleware import TenantMiddleware

        factory = RequestFactory()
        request = factory.get('/videos/')
        request.META['HTTP_HOST'] = 'ilovevoley.es'

        middleware = TenantMiddleware(lambda r: type('R', (), {'status_code': 200})())
        response = middleware(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')
