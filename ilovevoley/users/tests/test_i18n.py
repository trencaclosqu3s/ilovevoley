"""Soporte de idioma catalán (#291).

Protege la decisión de producto de que el cambio de idioma funcione sin prefijos
en la URL: la vista ``set_language`` fija la cookie estándar de Django y, con
sesión iniciada, sincroniza ``User.preferred_language``. El catálogo catalán se
comprueba contra cadenas reales de la interfaz, no contra el header del .po.
"""

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from ilovevoley.core.middleware import UserLanguageMiddleware


class SetLanguageViewTests(TestCase):
    """Al cambiar de idioma hay que fijar la cookie y persistir la preferencia."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='soci', password='pass',
        )

    def test_change_language_sets_cookie_for_anonymous_user(self):
        response = self.client.post(
            reverse('set_language'),
            {'language': 'ca', 'next': '/'},
        )

        self.assertRedirects(response, '/', fetch_redirect_response=False)
        self.assertEqual(response.cookies['django_language'].value, 'ca')

    def test_change_language_persists_preference_on_profile(self):
        self.client.force_login(self.user)

        self.client.post(
            reverse('set_language'),
            {'language': 'ca', 'next': '/'},
        )

        self.user.refresh_from_db()
        self.assertEqual(self.user.preferred_language, 'ca')

    def test_invalid_language_is_ignored(self):
        self.client.force_login(self.user)

        self.client.post(
            reverse('set_language'),
            {'language': 'de', 'next': '/'},
        )

        self.user.refresh_from_db()
        self.assertEqual(self.user.preferred_language, '')


class UserLanguageMiddlewareTests(TestCase):
    """La preferencia del perfil se aplica solo si no hay elección explícita."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='soci', password='pass', preferred_language='ca',
        )
        self.get_response = lambda request: None
        self.middleware = UserLanguageMiddleware(self.get_response)

    def tearDown(self):
        translation.deactivate()

    def _request(self, cookie=None, session=None):
        from django.test import RequestFactory
        request = RequestFactory().get('/')
        request.user = self.user
        request.COOKIES = {'django_language': cookie} if cookie else {}
        request.session = session or {}
        return request

    def test_applies_profile_language_without_explicit_choice(self):
        request = self._request()

        self.middleware(request)

        self.assertEqual(translation.get_language(), 'ca')
        self.assertEqual(request.LANGUAGE_CODE, 'ca')

    def test_cookie_wins_over_profile_language(self):
        request = self._request(cookie='es')

        self.middleware(request)

        self.assertNotEqual(translation.get_language(), 'ca')

    def test_anonymous_user_is_left_untouched(self):
        from django.contrib.auth.models import AnonymousUser
        request = self._request()
        request.user = AnonymousUser()

        self.middleware(request)

        self.assertNotEqual(translation.get_language(), 'ca')


class CatalanCatalogTests(TestCase):
    """El catálogo catalán debe traducir cadenas reales de la interfaz."""

    def test_template_renders_catalan_strings(self):
        with translation.override('ca'):
            html = render_to_string('account/password_reset.html')

        self.assertIn('Recuperar contrasenya', html)
        self.assertIn('Enviar enllaç de recuperació', html)
        self.assertNotIn('Enviar Enlace de Recuperación', html)

    def test_backend_strings_are_translated(self):
        with translation.override('ca'):
            from django.utils.translation import gettext as _

            self.assertEqual(_('Calendario de partidos'), 'Calendari de partits')


class ScriptTranslationEscapingTests(TestCase):
    """Un ``{% trans %}`` dentro de ``<script>`` debe ir con ``escapejs``.

    El catalán usa apóstrofos (``No s'ha pogut…``); sin escapar rompen el
    literal JS y el navegador descarta el script entero.
    """

    def test_trans_inside_script_blocks_is_escaped(self):
        import re
        from django.conf import settings

        files = (settings.BASE_DIR / 'ilovevoley').rglob('*.html')
        script = re.compile(r'<script\b[^>]*>(.*?)</script>', re.S)
        bare_trans = re.compile(r'\{%\s*(?:trans|translate)\s+"(?:[^"\\]|\\.)*"\s*%\}')
        offenders = [
            f for f in files
            for block in script.findall(f.read_text(encoding='utf-8'))
            if bare_trans.search(block)
        ]

        self.assertEqual(offenders, [])
