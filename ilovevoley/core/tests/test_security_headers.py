import re

from django.test import TestCase


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

    def test_csp_form_action_allows_only_google_login_redirect(self):
        """El login social hace POST -> 302 a Google; Chrome aplica form-action
        a esa redirección, así que accounts.google.com debe estar permitido
        (sin él el botón "Entrar con Google" se queda colgado en Chrome)."""
        response = self.client.get('/')
        form_action = self._directive(
            response.headers['Content-Security-Policy'], 'form-action'
        )
        self.assertEqual(
            form_action.split()[1:],
            ["'self'", 'https://accounts.google.com'],
        )

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

    @staticmethod
    def _directive(policy, name):
        for part in policy.split(';'):
            part = part.strip()
            if part.startswith(name + ' '):
                return part
        return ''
