import io
import re

from django.test import TestCase, override_settings
from django.core.management import call_command


class SecurityHeadersTest(TestCase):
    def test_csp_enforce_header_present(self):
        """La política CSP se emite en modo enforce (no Report-Only)."""
        response = self.client.get('/')
        self.assertIn('Content-Security-Policy', response.headers)
        self.assertNotIn('Content-Security-Policy-Report-Only', response.headers)

    def test_csp_public_policy_has_no_unsafe_inline_or_eval(self):
        """El sitio público no permite inline/eval: los inline van por nonce."""
        response = self.client.get('/')
        csp = response.headers['Content-Security-Policy']
        script_src = self._directive(csp, 'script-src')
        style_src = self._directive(csp, 'style-src')
        self.assertNotIn("'unsafe-inline'", script_src)
        self.assertNotIn("'unsafe-eval'", script_src)
        self.assertNotIn("'unsafe-inline'", style_src)
        self.assertIn("'nonce-", script_src)
        self.assertIn("'nonce-", style_src)

    def test_csp_safe_defaults(self):
        """Directivas de bloqueo estricto presentes y sin orígenes amplios."""
        response = self.client.get('/')
        csp = response.headers['Content-Security-Policy']
        self.assertIn("default-src 'self'", csp)
        self.assertIn("object-src 'none'", csp)
        self.assertIn("base-uri 'none'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertIn("form-action 'self'", csp)
        self.assertNotIn('tailwindcss', csp)
        self.assertNotIn('instagram', csp)

    def test_csp_nonce_in_header_matches_rendered_markup(self):
        """El nonce de la cabecera debe ser el mismo que usan los inline."""
        response = self.client.get('/')
        csp = response.headers['Content-Security-Policy']
        match = re.search(r"'nonce-([A-Za-z0-9_-]+)'", csp)
        self.assertIsNotNone(match)
        nonce = match.group(1)
        html = response.content.decode()
        self.assertIn(f'nonce="{nonce}"', html)

    def test_admin_uses_relaxed_csp(self):
        """El admin necesita inline/eval (Unfold/Alpine) y recibe política propia."""
        response = self.client.get('/admin/login/')
        self.assertEqual(response.status_code, 200)
        csp = response.headers['Content-Security-Policy']
        self.assertIn("'unsafe-inline'", csp)
        self.assertIn("'unsafe-eval'", csp)
        self.assertNotIn('Content-Security-Policy-Report-Only', response.headers)

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

    @staticmethod
    def _directive(policy, name):
        for part in policy.split(';'):
            part = part.strip()
            if part.startswith(name + ' '):
                return part
        return ''
