from django.test import TestCase
from django.contrib.auth import get_user_model
from ilovevoley.core.models import Organization
from ilovevoley.users.models import WebPushSubscription

User = get_user_model()


class WebPushSubscriptionModelTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='CV Teruel', slug='teruel')
        self.user = User.objects.create_user(username='volleyballer', email='voley@test.es')

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

    def test_notification_preference_default_is_enabled(self):
        from ilovevoley.users.models import NotificationPreference, NotificationType

        pref = NotificationPreference.objects.create(
            user=self.user,
            organization=self.org,
            notification_type=NotificationType.NEW_ALBUM,
        )
        self.assertTrue(pref.is_enabled)

