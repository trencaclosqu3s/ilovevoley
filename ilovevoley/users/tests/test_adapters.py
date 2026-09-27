from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount, SocialApp, SocialLogin
from allauth.socialaccount.providers.google.provider import GoogleProvider
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.cookie import CookieStorage
from django.test import RequestFactory, TestCase
from django.utils import translation

from ilovevoley.users.adapters import CustomAccountAdapter, CustomSocialAccountAdapter


class AddMessageSuppressionTest(TestCase):
    """La supresión de mensajes de login debe depender de la plantilla, no del texto.

    Con LANGUAGE_CODE = 'es-es' el contenido se traduce y la comparación contra
    cadenas en inglés dejaba de coincidir, propagando la cookie `messages`.
    """

    def setUp(self):
        self.adapter = CustomAccountAdapter()
        self.request = RequestFactory().get('/')
        self.request._messages = CookieStorage(self.request)

    def _messages(self):
        return [m.message for m in messages.get_messages(self.request)]

    def test_suppresses_login_message_with_spanish_language(self):
        with translation.override('es'):
            self.adapter.add_message(
                self.request,
                messages.SUCCESS,
                'account/messages/logged_in.txt',
                {'user': None},
            )

        self.assertEqual(self._messages(), [])

    def test_suppresses_account_connected_message(self):
        with translation.override('es'):
            self.adapter.add_message(
                self.request,
                messages.INFO,
                'socialaccount/messages/account_connected.txt',
                {'sociallogin': None, 'action': 'added'},
            )

        self.assertEqual(self._messages(), [])

    def test_keeps_unrelated_message(self):
        with translation.override('es'):
            self.adapter.add_message(
                self.request,
                messages.SUCCESS,
                'account/messages/password_changed.txt',
            )

        self.assertEqual(len(self._messages()), 1)


class AuthenticateByEmailTest(TestCase):
    """El login social solo puede absorber cuentas locales con email verificado.

    Sin esta restricción, cualquiera que registre el email de una víctima sin
    verificarlo se queda con esa cuenta cuando la víctima entra con Google.
    """

    def setUp(self):
        self.adapter = CustomSocialAccountAdapter()
        self.app = SocialApp.objects.create(
            provider='google', name='Google', client_id='cid', secret='secret'
        )
        self.provider = GoogleProvider(request=None, app=self.app)
        User = get_user_model()
        self.user = User.objects.create_user(
            username='local', email='victima@example.com', password='contrasena'
        )

    def _google_login(self):
        return SocialLogin(
            user=get_user_model()(),
            account=SocialAccount(provider='google', uid='google-uid'),
            provider=self.provider,
            email_addresses=[EmailAddress(email='victima@example.com', verified=True)],
        )

    def test_unverified_local_email_is_not_absorbed(self):
        EmailAddress.objects.create(
            user=self.user, email='victima@example.com', primary=True, verified=False
        )

        self.assertIsNone(self.adapter.authenticate_by_email(self._google_login()))

    def test_local_user_without_email_address_record_is_not_absorbed(self):
        self.assertIsNone(self.adapter.authenticate_by_email(self._google_login()))

    def test_verified_local_email_is_absorbed(self):
        EmailAddress.objects.create(
            user=self.user, email='victima@example.com', primary=True, verified=True
        )

        user, email = self.adapter.authenticate_by_email(self._google_login())

        self.assertEqual(user.pk, self.user.pk)
        self.assertEqual(email, 'victima@example.com')
