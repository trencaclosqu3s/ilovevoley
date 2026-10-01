from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from ilovevoley.core.models import Organization
from ilovevoley.users.models import WebPushSubscription

User = get_user_model()


class WebPushSubscriptionModelTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='CV Teruel', slug='teruel')
        self.user = User.objects.create_user(username='volleyballer', email='voley@test.es')

    def test_create_subscription(self):
        sub = WebPushSubscription.objects.create(
            user=self.user,
            organization=self.org,
            endpoint='https://fcm.googleapis.com/fcm/send/sample-token-123',
            p256dh='sample_p256dh_key',
            auth='sample_auth_secret',
            user_agent='Mozilla/5.0 PWA Test',
        )
        self.assertEqual(sub.user, self.user)
        self.assertEqual(sub.organization, self.org)
        self.assertIn('volleyballer', str(sub))

    def test_endpoint_must_be_unique(self):
        WebPushSubscription.objects.create(
            user=self.user,
            organization=self.org,
            endpoint='https://fcm.googleapis.com/fcm/send/duplicate',
            p256dh='key1',
            auth='auth1',
        )
        with self.assertRaises(IntegrityError):
            WebPushSubscription.objects.create(
                user=None,
                organization=self.org,
                endpoint='https://fcm.googleapis.com/fcm/send/duplicate',
                p256dh='key2',
                auth='auth2',
            )

    def test_anonymous_subscription_supported(self):
        sub = WebPushSubscription.objects.create(
            user=None,
            organization=self.org,
            endpoint='https://fcm.googleapis.com/fcm/send/anon-token',
            p256dh='key_anon',
            auth='auth_anon',
        )
        self.assertIsNone(sub.user)
        self.assertEqual(sub.organization, self.org)


class NotificationPreferenceModelTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='CV Teruel', slug='teruel')
        self.user = User.objects.create_user(username='volleyballer', email='voley@test.es')

    def test_create_notification_preference(self):
        from ilovevoley.users.models import NotificationPreference, NotificationType

        pref = NotificationPreference.objects.create(
            user=self.user,
            organization=self.org,
            notification_type=NotificationType.MATCH_RESULT,
            is_enabled=False,
        )
        self.assertEqual(pref.user, self.user)
        self.assertEqual(pref.organization, self.org)
        self.assertEqual(pref.notification_type, NotificationType.MATCH_RESULT)
        self.assertFalse(pref.is_enabled)
        self.assertIn('volleyballer', str(pref))

    def test_notification_preference_default_is_enabled(self):
        from ilovevoley.users.models import NotificationPreference, NotificationType

        pref = NotificationPreference.objects.create(
            user=self.user,
            organization=self.org,
            notification_type=NotificationType.NEW_ALBUM,
        )
        self.assertTrue(pref.is_enabled)

    def test_notification_preference_unique_together(self):
        from ilovevoley.users.models import NotificationPreference, NotificationType

        NotificationPreference.objects.create(
            user=self.user,
            organization=self.org,
            notification_type=NotificationType.MATCH_RESULT,
        )
        with self.assertRaises(IntegrityError):
            NotificationPreference.objects.create(
                user=self.user,
                organization=self.org,
                notification_type=NotificationType.MATCH_RESULT,
            )

