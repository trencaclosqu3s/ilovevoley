import json
from django.test import Client, TestCase, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from ilovevoley.core.models import Organization
from ilovevoley.users.models import WebPushSubscription

User = get_user_model()


@override_settings(ALLOWED_HOSTS=['santjust.ilovevoley.es', 'localhost', 'testserver'])
class WebPushViewsTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='CV Sant Just', slug='santjust')
        self.user = User.objects.create_user(username='jugadora', email='jugadora@test.es', password='password123')
        self.client = Client()

    def test_get_vapid_public_key(self):
        url = reverse('webpush_vapid_key')
        response = self.client.get(url, HTTP_HOST='santjust.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('public_key', data)
        self.assertTrue(len(data['public_key']) > 0)

    def test_subscribe_device_authenticated(self):
        self.client.login(username='jugadora', password='password123')
        url = reverse('webpush_subscribe')
        payload = {
            'endpoint': 'https://updates.push.services.mozilla.com/wpush/v2/gAAAAABsample',
            'keys': {
                'p256dh': 'BG_sample_key',
                'auth': 'secret_auth',
            },
            'user_agent': 'Mozilla/5.0 Test',
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_HOST='santjust.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get('success'))

        sub = WebPushSubscription.objects.get(endpoint=payload['endpoint'])
        self.assertEqual(sub.user, self.user)
        self.assertEqual(sub.organization, self.org)
        self.assertEqual(sub.p256dh, 'BG_sample_key')

    def test_subscribe_device_anonymous(self):
        url = reverse('webpush_subscribe')
        payload = {
            'endpoint': 'https://updates.push.services.mozilla.com/wpush/v2/anonymous-sub',
            'keys': {
                'p256dh': 'BG_anon_key',
                'auth': 'secret_anon_auth',
            },
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_HOST='santjust.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get('success'))

        sub = WebPushSubscription.objects.get(endpoint=payload['endpoint'])
        self.assertIsNone(sub.user)
        self.assertEqual(sub.organization, self.org)

    def test_subscribe_device_missing_fields(self):
        url = reverse('webpush_subscribe')
        payload = {
            'endpoint': 'https://updates.push.services.mozilla.com/wpush/v2/missing',
            'keys': {
                'p256dh': '',
                'auth': 'secret_auth',
            },
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_HOST='santjust.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 400)

    def test_subscribe_device_invalid_json(self):
        url = reverse('webpush_subscribe')
        response = self.client.post(
            url,
            data="not-valid-json",
            content_type='application/json',
            HTTP_HOST='santjust.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 400)

    def test_subscribe_device_relinks_when_updated(self):
        sub = WebPushSubscription.objects.create(
            user=None,
            organization=self.org,
            endpoint='https://updates.push.services.mozilla.com/token-relink',
            p256dh='old_key',
            auth='old_auth',
        )
        self.client.login(username='jugadora', password='password123')
        url = reverse('webpush_subscribe')
        payload = {
            'endpoint': 'https://updates.push.services.mozilla.com/token-relink',
            'keys': {
                'p256dh': 'new_key',
                'auth': 'new_auth',
            },
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_HOST='santjust.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        sub.refresh_from_db()
        self.assertEqual(sub.user, self.user)
        self.assertEqual(sub.p256dh, 'new_key')

    def test_unsubscribe_device(self):
        self.client.login(username='jugadora', password='password123')
        WebPushSubscription.objects.create(
            user=self.user,
            organization=self.org,
            endpoint='https://updates.push.services.mozilla.com/to-delete',
            p256dh='k',
            auth='a',
        )
        url = reverse('webpush_unsubscribe')
        payload = {'endpoint': 'https://updates.push.services.mozilla.com/to-delete'}
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_HOST='santjust.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(WebPushSubscription.objects.filter(endpoint=payload['endpoint']).exists())

    def test_unsubscribe_device_invalid_json(self):
        url = reverse('webpush_unsubscribe')
        response = self.client.post(
            url,
            data="invalid-json",
            content_type='application/json',
            HTTP_HOST='santjust.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 400)

    def test_subscribe_device_invalid_keys_type_returns_400(self):
        url = reverse('webpush_subscribe')
        payload = {
            'endpoint': 'https://updates.push.services.mozilla.com/wpush/v2/test-invalid-keys',
            'keys': 'invalid_string',
        }
        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_HOST='santjust.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 400)


    def test_subscribe_does_not_hijack_subscription_of_other_user(self):
        other = User.objects.create_user(username='otra', email='otra@test.es', password='password123')
        sub = WebPushSubscription.objects.create(
            user=other, organization=self.org,
            endpoint='https://push.example/owned', p256dh='k', auth='a',
        )
        self.client.login(username='jugadora', password='password123')
        response = self.client.post(
            reverse('webpush_subscribe'),
            data=json.dumps({'endpoint': sub.endpoint, 'keys': {'p256dh': 'x', 'auth': 'y'}}),
            content_type='application/json',
            HTTP_HOST='santjust.ilovevoley.es',
        )
        self.assertEqual(response.status_code, 403)
        sub.refresh_from_db()
        self.assertEqual(sub.user, other)
        self.assertEqual(sub.p256dh, 'k')

    def test_unsubscribe_does_not_delete_subscription_of_other_user(self):
        other = User.objects.create_user(username='otra', email='otra@test.es', password='password123')
        sub = WebPushSubscription.objects.create(
            user=other, organization=self.org,
            endpoint='https://push.example/owned', p256dh='k', auth='a',
        )
        self.client.login(username='jugadora', password='password123')
        self.client.post(
            reverse('webpush_unsubscribe'),
            data=json.dumps({'endpoint': sub.endpoint}),
            content_type='application/json',
            HTTP_HOST='santjust.ilovevoley.es',
        )
        self.assertTrue(WebPushSubscription.objects.filter(pk=sub.pk).exists())
