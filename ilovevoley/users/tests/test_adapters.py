from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount, SocialApp, SocialLogin
from allauth.socialaccount.providers.google.provider import GoogleProvider
from django.contrib.auth import get_user_model
from django.test import TestCase

from ilovevoley.users.adapters import CustomSocialAccountAdapter


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
