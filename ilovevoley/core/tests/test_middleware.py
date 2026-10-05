from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase, RequestFactory, override_settings
from django.core.cache import cache
from django.http import HttpResponseNotFound
from django.utils import timezone
from ilovevoley.core.middleware import (
    Error404TrackingMiddleware,
    day_cache_key,
    get_client_ip,
    send_404_daily_report,
    send_404_immediate_alert,
)


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


class Error404TrackingMiddlewareTest(TestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()

    def test_404_middleware_strips_query_string_from_url_and_logs(self):
        middleware = Error404TrackingMiddleware(lambda r: HttpResponseNotFound())
        request = self.factory.get('/nonexistent-page/?token=supersecret123&action=delete')
        request.user = type('AnonymousUser', (), {'is_authenticated': False})()

        with patch('ilovevoley.core.middleware.logger') as mock_logger:
            response = middleware(request)

        self.assertEqual(response.status_code, 404)

        # Verificar que el log no contiene la query string ni el token sensible
        mock_logger.warning.assert_called_once()
        log_message = mock_logger.warning.call_args[0][0]
        self.assertNotIn('supersecret123', log_message)
        self.assertNotIn('action=delete', log_message)
        self.assertIn('/nonexistent-page/', log_message)

        # Verificar que en cache se guarda la URL sin query string
        cache_key = day_cache_key('404_errors')
        errors = cache.get(cache_key, [])
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['url'], '/nonexistent-page/')

    def test_404_middleware_redacts_sensitive_tokens_in_path(self):
        middleware = Error404TrackingMiddleware(lambda r: HttpResponseNotFound())

        test_paths = [
            ('/moderate/user/secret-moderation-token-123/', '/moderate/user/[REDACTED]/'),
            ('/moderate/image/another-secret-token-456/', '/moderate/image/[REDACTED]/'),
            ('/calendario/suscripcion/user-cal-token-789/', '/calendario/suscripcion/[REDACTED]/'),
        ]

        for path, expected_sanitized in test_paths:
            with patch('ilovevoley.core.middleware.logger') as mock_logger:
                request = self.factory.get(path)
                request.user = type('AnonymousUser', (), {'is_authenticated': False})()
                middleware(request)

                log_message = mock_logger.warning.call_args[0][0]
                self.assertNotIn('secret', log_message)
                self.assertIn(expected_sanitized, log_message)

        cache_key = day_cache_key('404_errors')
        errors = cache.get(cache_key, [])
        recorded_urls = [e['url'] for e in errors]
        self.assertIn('/moderate/user/[REDACTED]/', recorded_urls)
        self.assertIn('/moderate/image/[REDACTED]/', recorded_urls)
        self.assertIn('/calendario/suscripcion/[REDACTED]/', recorded_urls)

    def test_404_middleware_sanitizes_referer(self):
        middleware = Error404TrackingMiddleware(lambda r: HttpResponseNotFound())
        request = self.factory.get('/some-missing-page/')
        request.user = type('AnonymousUser', (), {'is_authenticated': False})()
        request.META['HTTP_REFERER'] = 'https://ilovevoley.es/moderate/user/token999/?source=email&secret=xyz'

        middleware(request)

        cache_key = day_cache_key('404_errors')
        errors = cache.get(cache_key, [])
        self.assertEqual(len(errors), 1)
        self.assertNotIn('secret=xyz', errors[0]['referer'])
        self.assertNotIn('token999', errors[0]['referer'])
        self.assertEqual(errors[0]['referer'], 'https://ilovevoley.es/moderate/user/[REDACTED]/')

    def test_404_middleware_ignores_scanner_paths(self):
        """El ruido de escáneres/bots no cuenta, no se cachea ni se alerta (#237)."""
        middleware = Error404TrackingMiddleware(lambda r: HttpResponseNotFound())
        scanner_paths = [
            '/wp-login.php',
            '/wordpress/wp-admin/setup-config.php',
            '/phpmyadmin/index.php',
            '/.env',
            '/.git/config',
            '/cgi-bin/test.cgi',
            '/favicon.ico',
        ]

        with patch('ilovevoley.core.middleware.logger') as mock_logger, \
                patch('ilovevoley.core.middleware._atomic_incr') as mock_incr, \
                patch('ilovevoley.core.middleware.send_404_immediate_alert') as mock_alert:
            for path in scanner_paths:
                request = self.factory.get(path)
                request.user = AnonymousUser()
                middleware(request)

        mock_logger.warning.assert_not_called()
        mock_incr.assert_not_called()
        mock_alert.assert_not_called()

    def test_404_middleware_does_not_ignore_media_uploads(self):
        """Un .log subido por el usuario no debe filtrarse por la regla de extensiones."""
        middleware = Error404TrackingMiddleware(lambda r: HttpResponseNotFound())
        request = self.factory.get('/media/diagnostico.log')
        request.user = AnonymousUser()

        middleware(request)

        self.assertEqual(cache.get(day_cache_key('404_count')), 1)
        errors = cache.get(day_cache_key('404_errors'), [])
        self.assertEqual(errors[0]['url'], '/media/diagnostico.log')

    def test_404_middleware_does_not_ignore_wordpress_substring(self):
        """Una ruta legítima que contenga 'wordpress' en un segmento no debe silenciarse."""
        middleware = Error404TrackingMiddleware(lambda r: HttpResponseNotFound())
        request = self.factory.get('/api/wordpress-bridge/v2')
        request.user = AnonymousUser()

        middleware(request)

        self.assertEqual(cache.get(day_cache_key('404_count')), 1)

    def test_404_middleware_uses_atomic_increment(self):
        middleware = Error404TrackingMiddleware(lambda r: HttpResponseNotFound())
        request = self.factory.get('/not-found-page/')
        request.user = type('AnonymousUser', (), {'is_authenticated': False})()

        daily_count_key = day_cache_key('404_count')

        # Disparar 3 errores 404
        middleware(request)
        middleware(request)
        middleware(request)

        self.assertEqual(cache.get(daily_count_key), 3)

    @override_settings(
        NOTIFICATION_EMAIL_ENABLED=True,
        EMAIL_NOTIFICATIONS={'error_404_daily': True},
        DEFAULT_FROM_EMAIL='test@ilovevoley.es',
    )
    def test_send_404_daily_report_uses_daily_count_and_sanitized_urls(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        User.objects.create_superuser('admin_test_404', 'admin_test_404@example.com', 'pass1234')

        yesterday = timezone.localtime(timezone.now()) - timedelta(days=1)
        cache_key = day_cache_key('404_errors', yesterday)
        daily_count_key = day_cache_key('404_count', yesterday)

        cache.set(cache_key, [
            {
                'url': '/not-found/',
                'method': 'GET',
                'ip': '127.0.0.1',
                'user_agent': 'TestAgent',
                'referer': '',
                'timestamp': yesterday.isoformat(),
                'user': 'Anonymous',
            }
        ])
        cache.set(daily_count_key, 42)

        with patch('ilovevoley.core.middleware.send_mail') as mock_send_mail:
            result = send_404_daily_report()

        self.assertTrue(result)
        mock_send_mail.assert_called_once()
        call_kwargs = mock_send_mail.call_args[1]
        self.assertIn('admin_test_404@example.com', call_kwargs['recipient_list'])
        self.assertIn('/not-found/', call_kwargs['html_message'])
        self.assertIn('42', call_kwargs['html_message'])

    @override_settings(
        NOTIFICATION_EMAIL_ENABLED=True,
        EMAIL_NOTIFICATIONS={'error_404_daily': True},
        DEFAULT_FROM_EMAIL='test@ilovevoley.es',
        TECHNICAL_ALERT_EMAILS=['tech@ilovevoley.es'],
    )
    def test_404_report_ignores_superusers_when_technical_list_is_set(self):
        """Regla de negocio: los 404 van a la lista técnica, no a todo superuser.

        Un superuser puede existir solo para gestionar contenido; los avisos de
        infraestructura no le corresponden.
        """
        from django.contrib.auth import get_user_model
        User = get_user_model()
        User.objects.create_superuser('content_admin_404', 'content_admin_404@example.com', 'pass1234')

        yesterday = timezone.localtime(timezone.now()) - timedelta(days=1)
        cache.set(day_cache_key('404_errors', yesterday), [
            {
                'url': '/not-found/',
                'method': 'GET',
                'ip': '127.0.0.1',
                'user_agent': 'TestAgent',
                'referer': '',
                'timestamp': yesterday.isoformat(),
                'user': 'Anonymous',
            }
        ])

        with patch('ilovevoley.core.middleware.send_mail') as mock_send_mail:
            self.assertTrue(send_404_daily_report())

        recipients = mock_send_mail.call_args[1]['recipient_list']
        self.assertEqual(recipients, ['tech@ilovevoley.es'])
        self.assertNotIn('content_admin_404@example.com', recipients)

    @override_settings(
        NOTIFICATION_EMAIL_ENABLED=True,
        DEFAULT_FROM_EMAIL='test@ilovevoley.es',
    )
    def test_send_404_immediate_alert_threshold(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        User.objects.create_superuser('admin_alert_404', 'admin_alert_404@example.com', 'pass1234')

        request = self.factory.get('/some-path/?token=hidden')

        # El middleware encola la alerta; el envío SMTP ocurre en la tarea Celery.
        with patch('ilovevoley.core.tasks.send_404_immediate_alert_task.delay') as mock_delay:
            r1 = send_404_immediate_alert(request, threshold=3)
            self.assertFalse(r1)
            mock_delay.assert_not_called()

            r2 = send_404_immediate_alert(request, threshold=3)
            self.assertFalse(r2)
            mock_delay.assert_not_called()

            r3 = send_404_immediate_alert(request, threshold=3)
            self.assertTrue(r3)
            mock_delay.assert_called_once()
            count, hour, last_url, recipients = mock_delay.call_args[0]
            self.assertEqual(count, 3)
            self.assertNotIn('token=hidden', last_url)
            self.assertIn('/some-path/', last_url)
            self.assertIn('admin_alert_404@example.com', recipients)

    def test_sanitize_path_redacts_share_token(self):
        from ilovevoley.core.middleware import sanitize_path
        self.assertEqual(
            sanitize_path('/p/partido/123e4567-e89b-12d3-a456-426614174000/'),
            '/p/partido/[REDACTED]/',
        )
        self.assertEqual(
            sanitize_path('/p/partido/123e4567-e89b-12d3-a456-426614174000/media/5/'),
            '/p/partido/[REDACTED]/media/5/',
        )


class GetClientIPTests(TestCase):
    """La IP fiable es la que añade nginx al final; lo forjado por el cliente se descarta."""

    def setUp(self):
        self.factory = RequestFactory()

    def _request(self, remote_addr='172.18.0.5', forwarded_for=None):
        request = self.factory.get('/')
        request.META['REMOTE_ADDR'] = remote_addr
        if forwarded_for is not None:
            request.META['HTTP_X_FORWARDED_FOR'] = forwarded_for
        return request

    def test_discards_forged_prefix_and_returns_real_client(self):
        request = self._request(forwarded_for='9.9.9.9, 203.0.113.7')
        self.assertEqual(get_client_ip(request), '203.0.113.7')

    def test_discards_every_forged_entry(self):
        request = self._request(forwarded_for='9.9.9.9, 8.8.8.8, 203.0.113.7')
        self.assertEqual(get_client_ip(request), '203.0.113.7')

    def test_never_returns_internal_docker_ip_when_header_present(self):
        request = self._request(remote_addr='172.18.0.5', forwarded_for='9.9.9.9, 203.0.113.7')
        self.assertNotEqual(get_client_ip(request), '172.18.0.5')
        self.assertEqual(get_client_ip(request), '203.0.113.7')

    def test_falls_back_to_remote_addr_without_header(self):
        request = self._request(remote_addr='203.0.113.7')
        self.assertEqual(get_client_ip(request), '203.0.113.7')

    def test_skips_malformed_entries(self):
        request = self._request(forwarded_for='not-an-ip, , 203.0.113.7')
        self.assertEqual(get_client_ip(request), '203.0.113.7')

    def test_handles_ipv4_with_port_and_bracketed_ipv6(self):
        self.assertEqual(get_client_ip(self._request(forwarded_for='203.0.113.7:443')), '203.0.113.7')
        self.assertEqual(get_client_ip(self._request(forwarded_for='[2001:db8::1]:443')), '2001:db8::1')

    def test_normalizes_ipv6(self):
        request = self._request(forwarded_for='2001:0db8::0001')
        self.assertEqual(get_client_ip(request), '2001:db8::1')

    @override_settings(TRUSTED_PROXY_COUNT=2)
    def test_respects_configured_proxy_count(self):
        request = self._request(forwarded_for='9.9.9.9, 203.0.113.7, 10.0.0.1')
        self.assertEqual(get_client_ip(request), '203.0.113.7')

    @override_settings(TRUSTED_PROXY_COUNT=2)
    def test_chain_shorter_than_proxy_count_falls_back_to_remote_addr(self):
        request = self._request(remote_addr='172.18.0.5', forwarded_for='203.0.113.7')
        self.assertEqual(get_client_ip(request), '172.18.0.5')
