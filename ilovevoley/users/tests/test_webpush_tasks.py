from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from pywebpush import WebPushException
from ilovevoley.core.models import Category, Organization
from ilovevoley.users.models import CategoryPreference, WebPushSubscription
from ilovevoley.users.webpush import send_web_push
from ilovevoley.users.tasks import (
    notify_web_push_subscription_task,
    notify_web_push_user_task,
    notify_web_push_organization_task,
)

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

    @patch('ilovevoley.users.tasks.send_web_push')
    def test_notify_web_push_subscription_task(self, mock_send):
        mock_send.return_value = True
        result = notify_web_push_subscription_task(
            subscription_id=self.sub.id,
            payload={'title': 'Test Direct'},
        )
        self.assertTrue(result)
        mock_send.assert_called_once_with(self.sub, {'title': 'Test Direct'})

    def test_notify_web_push_subscription_task_nonexistent(self):
        result = notify_web_push_subscription_task(
            subscription_id=999999,
            payload={'title': 'Test Direct'},
        )
        self.assertFalse(result)

    @patch('ilovevoley.users.tasks.send_web_push')
    def test_notify_web_push_user_task(self, mock_send):
        mock_send.return_value = True
        notify_web_push_user_task(
            user_id=self.user.id,
            title='Próximo Partido',
            body='Mañana a las 18:00',
            url='/partidos/1/',
            badge_count=2,
        )
        mock_send.assert_called_once()
        args, _ = mock_send.call_args
        self.assertEqual(args[0], self.sub)
        self.assertEqual(args[1]['title'], 'Próximo Partido')
        self.assertEqual(args[1]['badge_count'], 2)

    @patch('ilovevoley.users.tasks.send_web_push')
    def test_notify_web_push_user_task_filtered_by_organization(self, mock_send):
        mock_send.return_value = True
        other_org = Organization.objects.create(name='Other Club', slug='other')

        # Con organization_id coincidente
        dispatched = notify_web_push_user_task(
            user_id=self.user.id,
            title='Próximo Partido',
            body='Mañana a las 18:00',
            organization_id=self.org.id,
        )
        self.assertEqual(dispatched, 1)

        # Con organization_id no coincidente
        dispatched_other = notify_web_push_user_task(
            user_id=self.user.id,
            title='Próximo Partido',
            body='Mañana a las 18:00',
            organization_id=other_org.id,
        )
        self.assertEqual(dispatched_other, 0)

    @patch('ilovevoley.users.tasks.send_web_push')
    def test_notify_web_push_organization_task(self, mock_send):
        mock_send.return_value = True
        notify_web_push_organization_task(
            organization_id=self.org.id,
            title='Nuevo Álbum',
            body='Fotos del derbi disponibles',
            url='/galeria/',
        )
        mock_send.assert_called_once()


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
