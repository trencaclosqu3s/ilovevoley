from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from py_vapid import Vapid
from pywebpush import WebPushException
from ilovevoley.core.models import Category, Organization
from ilovevoley.users.models import CategoryPreference, NotificationPreference, NotificationType, WebPushSubscription
from ilovevoley.users.webpush import send_web_push
from ilovevoley.users.tasks import notify_web_push_organization_task

User = get_user_model()


class WebPushTasksTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='CV Sant Just', slug='santjust')
        self.user = User.objects.create_user(username='testplayer', email='tp@test.es')
        self.sub = WebPushSubscription.objects.create(
            user=self.user,
            organization=self.org,
            endpoint='https://fcm.googleapis.com/fcm/send/active-token',
            p256dh='test_p256dh',
            auth='test_auth',
        )

    @patch('ilovevoley.users.webpush.pywebpush_send')
    def test_send_web_push_accepts_pem_private_key(self, mock_webpush):
        # pywebpush trata un str como base64 DER, no como PEM: hay que pasarle un Vapid.
        vapid = Vapid()
        vapid.generate_keys()
        pem_text = vapid.private_pem().decode()
        with override_settings(VAPID_PRIVATE_KEY=pem_text):
            self.assertTrue(send_web_push(self.sub, {'title': 'Aviso'}))
        self.assertIsInstance(mock_webpush.call_args.kwargs['vapid_private_key'], Vapid)

    @override_settings(VAPID_PRIVATE_KEY='test-private-key')
    @patch('ilovevoley.users.webpush.pywebpush_send')
    def test_send_web_push_success(self, mock_webpush):
        mock_webpush.return_value = MagicMock(status_code=201)
        payload = {'title': 'Resultado Final', 'body': 'Ganamos 3-1'}
        result = send_web_push(self.sub, payload)
        self.assertTrue(result)
        mock_webpush.assert_called_once()

    @override_settings(VAPID_PRIVATE_KEY='test-private-key')
    @patch('ilovevoley.users.webpush.pywebpush_send')
    def test_send_web_push_cleans_up_expired_subscription_410(self, mock_webpush):
        response_mock = MagicMock(status_code=410)
        mock_webpush.side_effect = WebPushException('Subscription gone', response=response_mock)

        result = send_web_push(self.sub, {'title': 'Aviso'})
        self.assertFalse(result)
        # La suscripción debe ser eliminada de la base de datos automáticamente
        self.assertFalse(WebPushSubscription.objects.filter(pk=self.sub.pk).exists())

    @override_settings(VAPID_PRIVATE_KEY='test-private-key')
    @patch('ilovevoley.users.webpush.pywebpush_send')
    def test_send_web_push_cleans_up_not_found_subscription_404(self, mock_webpush):
        response_mock = MagicMock(status_code=404)
        mock_webpush.side_effect = WebPushException('Not found', response=response_mock)

        result = send_web_push(self.sub, {'title': 'Aviso'})
        self.assertFalse(result)
        self.assertFalse(WebPushSubscription.objects.filter(pk=self.sub.pk).exists())

    @override_settings(VAPID_PRIVATE_KEY='')
    def test_send_web_push_missing_vapid_key_returns_false(self):
        result = send_web_push(self.sub, {'title': 'Aviso'})
        self.assertFalse(result)
        # La suscripción no se borra si falta la clave de configuración
        self.assertTrue(WebPushSubscription.objects.filter(pk=self.sub.pk).exists())

    @override_settings(VAPID_PRIVATE_KEY='test-private-key')
    @patch('ilovevoley.users.webpush.pywebpush_send')
    def test_send_web_push_other_exception_does_not_delete_subscription(self, mock_webpush):
        response_mock = MagicMock(status_code=500)
        mock_webpush.side_effect = WebPushException('Internal server error', response=response_mock)

        result = send_web_push(self.sub, {'title': 'Aviso'})
        self.assertFalse(result)
        self.assertTrue(WebPushSubscription.objects.filter(pk=self.sub.pk).exists())

    @override_settings(VAPID_PRIVATE_KEY='test-private-key')
    @patch('ilovevoley.users.webpush.pywebpush_send')
    def test_send_web_push_network_exception_returns_false_and_preserves_subscription(self, mock_webpush):
        mock_webpush.side_effect = ConnectionError('Network connection reset')

        result = send_web_push(self.sub, {'title': 'Aviso'})
        self.assertFalse(result)
        self.assertTrue(WebPushSubscription.objects.filter(pk=self.sub.pk).exists())


class WebPushCategoryFilterTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='CV Sant Just', slug='santjust')
        self.infantil = Category.objects.create(name='Infantil')
        self.senior = Category.objects.create(name='Sénior')

    def _sub(self, name, user, endpoint_suffix=None):
        return WebPushSubscription.objects.create(
            user=user, organization=self.org,
            endpoint=f'https://push.example/{name}', p256dh='k', auth='a',
        )

    def _user(self, name, categories=None):
        user = User.objects.create_user(username=name, email=f'{name}@test.es')
        if categories is not None:
            CategoryPreference.objects.create(user=user, organization=self.org).categories.set(categories)
        return user

    @patch('ilovevoley.users.tasks.send_web_push', return_value=True)
    def test_organization_push_filters_by_category_preferences(self, mock_send):
        self._sub('match', self._user('match', [self.infantil]))
        self._sub('other', self._user('other', [self.senior]))
        self._sub('nopref', self._user('nopref'))
        self._sub('anon', None)

        notify_web_push_organization_task(
            organization_id=self.org.id, title='t', body='b', category_ids=[self.infantil.id],
        )

        notified = {call.args[0].endpoint.rsplit('/', 1)[1] for call in mock_send.call_args_list}
        self.assertEqual(notified, {'match', 'nopref', 'anon'})


class WebPushNotificationTypeFilterTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='CV Sant Just', slug='santjust')
        self.other_org = Organization.objects.create(name='Other Club', slug='other')
        self.cat_infantil = Category.objects.create(name='Infantil')
        self.cat_cadete = Category.objects.create(name='Cadete')

    def _sub(self, name, user):
        return WebPushSubscription.objects.create(
            user=user,
            organization=self.org,
            endpoint=f'https://push.example/{name}',
            p256dh='k',
            auth='a',
        )

    def _user(self, name):
        return User.objects.create_user(username=name, email=f'{name}@test.es')

    @patch('ilovevoley.users.tasks.send_web_push', return_value=True)
    def test_push_filters_by_notification_type(self, mock_send):
        # user_active: tiene preferencia activa explícita
        u_active = self._user('u_active')
        NotificationPreference.objects.create(
            user=u_active,
            organization=self.org,
            notification_type=NotificationType.MATCH_RESULT,
            is_enabled=True,
        )
        self._sub('sub_active', u_active)

        # user_disabled: tiene preferencia desactivada explícita para MATCH_RESULT
        u_disabled = self._user('u_disabled')
        NotificationPreference.objects.create(
            user=u_disabled,
            organization=self.org,
            notification_type=NotificationType.MATCH_RESULT,
            is_enabled=False,
        )
        self._sub('sub_disabled', u_disabled)

        # user_nopref: no tiene preferencias (debe recibirlo por defecto)
        u_nopref = self._user('u_nopref')
        self._sub('sub_nopref', u_nopref)

        # anon: sin usuario (debe recibirlo)
        self._sub('sub_anon', None)

        # user_other_org: desactivó MATCH_RESULT en OTRO club, pero no en este
        u_other_org = self._user('u_other_org')
        NotificationPreference.objects.create(
            user=u_other_org,
            organization=self.other_org,
            notification_type=NotificationType.MATCH_RESULT,
            is_enabled=False,
        )
        self._sub('sub_other_org', u_other_org)

        notify_web_push_organization_task(
            organization_id=self.org.id,
            title='Resultado final',
            body='3-1',
            notification_type=NotificationType.MATCH_RESULT,
        )

        notified = {call.args[0].endpoint.rsplit('/', 1)[1] for call in mock_send.call_args_list}
        # sub_disabled no debe recibirlo; los demás sí
        self.assertEqual(notified, {'sub_active', 'sub_nopref', 'sub_anon', 'sub_other_org'})

    @patch('ilovevoley.users.tasks.send_web_push', return_value=True)
    def test_push_combines_category_and_notification_type_filters(self, mock_send):
        # u1: sigue categoría Infantil y tiene MATCH_RESULT activo -> recibe
        u1 = self._user('u1')
        CategoryPreference.objects.create(user=u1, organization=self.org).categories.set([self.cat_infantil])
        NotificationPreference.objects.create(
            user=u1, organization=self.org, notification_type=NotificationType.MATCH_RESULT, is_enabled=True,
        )
        self._sub('sub_u1', u1)

        # u2: sigue categoría Infantil pero tiene MATCH_RESULT desactivado -> NO recibe
        u2 = self._user('u2')
        CategoryPreference.objects.create(user=u2, organization=self.org).categories.set([self.cat_infantil])
        NotificationPreference.objects.create(
            user=u2, organization=self.org, notification_type=NotificationType.MATCH_RESULT, is_enabled=False,
        )
        self._sub('sub_u2', u2)

        # u3: sigue categoría Cadete (no Infantil) y MATCH_RESULT activo -> NO recibe por categoría
        u3 = self._user('u3')
        CategoryPreference.objects.create(user=u3, organization=self.org).categories.set([self.cat_cadete])
        self._sub('sub_u3', u3)

        # u4: sin preferencia de categoría ni de tipo -> recibe
        u4 = self._user('u4')
        self._sub('sub_u4', u4)

        # anon: anónimo -> recibe
        self._sub('sub_anon', None)

        notify_web_push_organization_task(
            organization_id=self.org.id,
            title='Resultado final',
            body='3-1',
            category_ids=[self.cat_infantil.id],
            notification_type=NotificationType.MATCH_RESULT,
        )

        notified = {call.args[0].endpoint.rsplit('/', 1)[1] for call in mock_send.call_args_list}
        self.assertEqual(notified, {'sub_u1', 'sub_u4', 'sub_anon'})

