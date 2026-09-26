from django.test import TestCase, override_settings
from django.core.management import call_command
from django.utils.csp import CSP
import io


class SecurityHeadersTest(TestCase):
    def test_csp_report_only_header_present(self):
        """Verifica que el middleware añade la cabecera Content-Security-Policy-Report-Only."""
        response = self.client.get('/')
        self.assertIn('Content-Security-Policy-Report-Only', response.headers)
        self.assertNotIn('Content-Security-Policy', response.headers)

        csp = response.headers['Content-Security-Policy-Report-Only']
        self.assertIn("default-src 'self'", csp)
        self.assertIn("https://cdn.tailwindcss.com", csp)
        self.assertIn("https://cdn.jsdelivr.net", csp)
        self.assertIn("https://cdnjs.cloudflare.com", csp)
        self.assertIn("https://www.youtube-nocookie.com", csp)
        self.assertIn("object-src 'none'", csp)

    @override_settings(
        SECURE_HSTS_SECONDS=31536000,
        SECURE_HSTS_INCLUDE_SUBDOMAINS=True,
    )
    def test_hsts_header_on_secure_request(self):
        """Verifica que la cabecera Strict-Transport-Security se emite en peticiones HTTPS con HSTS activo."""
        response = self.client.get('/', secure=True)
        self.assertIn('Strict-Transport-Security', response.headers)
        hsts = response.headers['Strict-Transport-Security']
        self.assertIn('max-age=31536000', hsts)
        self.assertIn('includeSubDomains', hsts)

    def test_production_deployment_check_no_transport_warnings(self):
        """Verifica que check --deploy en configuración de producción no emite avisos de transporte seguro."""
        out = io.StringIO()
        with override_settings(
            DEBUG=False,
            SECRET_KEY='django-insecure-test-key-with-sufficient-entropy-for-deploy-check-1234567890',
            ALLOWED_HOSTS=['ilovevoley.es'],
            SESSION_COOKIE_SECURE=True,
            CSRF_COOKIE_SECURE=True,
            SECURE_SSL_REDIRECT=True,
            SECURE_HSTS_SECONDS=31536000,
            SECURE_HSTS_INCLUDE_SUBDOMAINS=True,
        ):
            call_command('check', '--deploy', stdout=out, stderr=out)

        output = out.getvalue()
        self.assertNotIn('security.W004', output)
        self.assertNotIn('security.W008', output)
        self.assertNotIn('security.W012', output)
        self.assertNotIn('security.W016', output)
