from datetime import datetime, timedelta
from unittest.mock import patch
from django.test import TestCase, RequestFactory, override_settings
from django.core.cache import cache
from django.http import HttpResponseNotFound
from ilovevoley.core.middleware import (
    Error404TrackingMiddleware,
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
        today = datetime.now().strftime('%Y%m%d')
        cache_key = f'404_errors_{today}'
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

        today = datetime.now().strftime('%Y%m%d')
        cache_key = f'404_errors_{today}'
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

        today = datetime.now().strftime('%Y%m%d')
        cache_key = f'404_errors_{today}'
        errors = cache.get(cache_key, [])
        self.assertEqual(len(errors), 1)
        self.assertNotIn('secret=xyz', errors[0]['referer'])
        self.assertNotIn('token999', errors[0]['referer'])
        self.assertEqual(errors[0]['referer'], 'https://ilovevoley.es/moderate/user/[REDACTED]/')

    def test_404_middleware_uses_atomic_increment(self):
        middleware = Error404TrackingMiddleware(lambda r: HttpResponseNotFound())
        request = self.factory.get('/not-found-page/')
        request.user = type('AnonymousUser', (), {'is_authenticated': False})()

        today = datetime.now().strftime('%Y%m%d')
        daily_count_key = f'404_count_{today}'

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

        yesterday = datetime.now() - timedelta(days=1)
        cache_key = f"404_errors_{yesterday.strftime('%Y%m%d')}"
        daily_count_key = f"404_count_{yesterday.strftime('%Y%m%d')}"

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


class CacheSettingsTest(TestCase):
    def test_redis_cache_configured(self):
        """Prod define Redis; pytest usa LocMem vía config.settings_test."""
        import config.settings as prod_settings
        from django.conf import settings

        self.assertEqual(
            prod_settings.CACHES['default']['BACKEND'],
            'django.core.cache.backends.redis.RedisCache',
        )
        self.assertTrue(
            prod_settings.CACHES['default']['LOCATION'].startswith('redis://')
        )
        self.assertEqual(
            settings.CACHES['default']['BACKEND'],
            'django.core.cache.backends.locmem.LocMemCache',
        )
