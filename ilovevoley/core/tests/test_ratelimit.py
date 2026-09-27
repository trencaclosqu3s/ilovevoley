import json
from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django_ratelimit.exceptions import Ratelimited

from ilovevoley.core.middleware import get_client_ip as middleware_get_client_ip
from ilovevoley.core.ratelimit_utils import get_client_ip
from ilovevoley.core.views import custom_429


class ClientIPDelegationTests(TestCase):
    """ratelimit_utils delega en el middleware anti-spoofing, no reimplementa la IP."""

    def test_ratelimit_utils_reexports_middleware_get_client_ip(self):
        self.assertIs(get_client_ip, middleware_get_client_ip)

    def test_uses_last_trusted_hop_not_client_prefix(self):
        factory = RequestFactory()
        request = factory.get(
            '/', REMOTE_ADDR='172.18.0.5',
            HTTP_X_FORWARDED_FOR='9.9.9.9, 203.0.113.7',
        )
        self.assertEqual(get_client_ip(request), '203.0.113.7')


class Custom429HandlerTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_custom_429_html_response(self):
        request = self.factory.get('/test/')
        response = custom_429(request, exception=Ratelimited())
        self.assertEqual(response.status_code, 429)
        self.assertIn(b'429', response.content)
        self.assertIn('Tiempo de descanso'.encode('utf-8'), response.content)

    def test_custom_429_json_response_for_ajax(self):
        request = self.factory.get('/test/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        response = custom_429(request, exception=Ratelimited())
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response['Content-Type'], 'application/json')
        data = json.loads(response.content.decode('utf-8'))
        self.assertIn('error', data)
        self.assertIn('detail', data)

    def test_custom_429_json_response_for_accept_json(self):
        request = self.factory.get('/test/', HTTP_ACCEPT='application/json')
        response = custom_429(request, exception=Ratelimited())
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response['Content-Type'], 'application/json')


class RatelimitMiddlewareTests(TestCase):
    def test_middleware_catches_ratelimited_exception(self):
        from django_ratelimit.middleware import RatelimitMiddleware

        def raising_view(request):
            raise Ratelimited()

        middleware = RatelimitMiddleware(raising_view)
        factory = RequestFactory()
        request = factory.get('/')
        response = middleware.process_exception(request, Ratelimited())
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 429)

    def test_preview_429_view(self):
        from ilovevoley.core.views import test_429

        factory = RequestFactory()
        request = factory.get('/test-error/429/')
        response = test_429(request)
        self.assertEqual(response.status_code, 429)
        self.assertIn(b'429', response.content)
        self.assertIn('Tiempo de descanso'.encode('utf-8'), response.content)


@override_settings(
    RATELIMIT_ENABLE=True,
    RATELIMIT_USE_CACHE='default',
)
class ModerationRateLimitingTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_moderate_user_rate_limiting_by_ip(self):
        url = '/moderate/user/some-token-string/'
        client_ip = '198.51.100.90'

        # 10 peticiones dentro del límite (redirige a login o 400 si no autenticado)
        for i in range(10):
            response = self.client.get(url, REMOTE_ADDR=client_ip)
            self.assertNotEqual(response.status_code, 429)

        # 11ª petición bloqueada con 429
        blocked_response = self.client.get(url, REMOTE_ADDR=client_ip)
        self.assertEqual(blocked_response.status_code, 429)

    def test_moderate_image_rate_limiting_by_ip(self):
        url = '/moderate/image/some-token-string/'
        client_ip = '198.51.100.91'

        for i in range(10):
            response = self.client.get(url, REMOTE_ADDR=client_ip)
            self.assertNotEqual(response.status_code, 429)

        blocked_response = self.client.get(url, REMOTE_ADDR=client_ip)
        self.assertEqual(blocked_response.status_code, 429)
