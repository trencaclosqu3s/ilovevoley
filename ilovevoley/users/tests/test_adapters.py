from datetime import timedelta

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount, SocialApp, SocialLogin
from allauth.socialaccount.providers.google.provider import GoogleProvider
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.cookie import CookieStorage
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation

from ilovevoley.core.models import Organization
from ilovevoley.core.tenant_utils import approve_user_membership
from ilovevoley.users.adapters import CustomAccountAdapter, CustomSocialAccountAdapter
from ilovevoley.users.models import Membership

User = get_user_model()


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

    def test_suppresses_known_login_messages_in_spanish(self):
        with translation.override('es'):
            self.adapter.add_message(
                self.request,
                messages.SUCCESS,
                'account/messages/logged_in.txt',
                {'user': None},
            )
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


@override_settings(
    ALLOWED_HOSTS=['cluba.ilovevoley.es'],
    LOGIN_PROFILE_REVIEW_INACTIVITY_DAYS=90,
)
class LoginProfileReviewTest(TestCase):
    """Primer login tras la aprobación, o tras 90 días sin entrar, aterriza en el perfil (#544).

    Regla de negocio con efecto persistente: la marca de revisión se consume al
    llegar al perfil, de modo que el login siguiente vuelve a la home del club.
    Un ``next`` explícito (enlace protegido) manda sobre el perfil.
    """

    HOST = 'cluba.ilovevoley.es'

    def setUp(self):
        cache.clear()
        self.org = Organization.objects.create(slug='cluba', name='Club A')
        self.user = User.objects.create_user(
            username='socio', email='socio@test.com', password='ComplexPass123!',
            is_approved=False,
        )
        Membership.objects.create(user=self.user, organization=self.org, is_approved=False)
        # El landing del club manda al login con la home como `next`.
        self.home = reverse(self.org.home_url_name)

    def _login(self, next_url=None):
        data = {'login': 'socio', 'password': 'ComplexPass123!'}
        if next_url is not None:
            data['next'] = next_url
        return self.client.post(reverse('account_login'), data, HTTP_HOST=self.HOST)

    def test_first_login_after_approval_lands_on_profile_and_consumes_mark(self):
        approve_user_membership(self.user, self.org)

        response = self._login(next_url=self.home)

        self.assertEqual(response['Location'], reverse('profile'))
        self.user.refresh_from_db()
        self.assertFalse(self.user.pending_profile_review)

    def test_login_without_next_reviews_the_profile(self):
        """El login directo, sin `next`, también revisa el perfil: el destino por
        defecto de allauth es otra «home» que cede ante la revisión."""
        approve_user_membership(self.user, self.org)

        response = self._login()

        self.assertEqual(response['Location'], reverse('profile'))

    def test_next_login_goes_back_to_the_tenant_home(self):
        approve_user_membership(self.user, self.org)
        self._login(next_url=self.home)

        response = self._login(next_url=self.home)

        self.assertEqual(response['Location'], self.home)

    def test_login_after_the_inactivity_threshold_lands_on_profile(self):
        self.user.is_approved = True
        self.user.last_login = timezone.now() - timedelta(days=90)
        self.user.save(update_fields=['is_approved', 'last_login'])

        response = self._login(next_url=self.home)

        self.assertEqual(response['Location'], reverse('profile'))

    def test_login_before_the_inactivity_threshold_keeps_the_tenant_home(self):
        self.user.is_approved = True
        self.user.last_login = timezone.now() - timedelta(days=89)
        self.user.save(update_fields=['is_approved', 'last_login'])

        response = self._login(next_url=self.home)

        self.assertEqual(response['Location'], self.home)

    def test_explicit_next_wins_over_the_profile(self):
        approve_user_membership(self.user, self.org)
        target = reverse('rosters:roster_overview')

        response = self._login(next_url=target)

        self.assertEqual(response['Location'], target)
        # La revisión no se da por hecha: se ofrecerá en un login que sí vaya a la home.
        self.user.refresh_from_db()
        self.assertTrue(self.user.pending_profile_review)

