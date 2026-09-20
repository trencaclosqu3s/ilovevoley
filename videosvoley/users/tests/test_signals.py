from django.contrib.auth import get_user_model
from django.core import mail
from django.test import RequestFactory, TestCase, override_settings

from allauth.account.signals import user_signed_up
from videosvoley.core.email_utils import get_moderation_recipients
from videosvoley.users.signals import send_new_user_notification


@override_settings(ALLOWED_HOSTS=['cluba.ilovevoley.es', 'clubb.ilovevoley.es'])
class ModerationRecipientsTest(TestCase):
    def setUp(self):
        from videosvoley.core.models import Organization
        from videosvoley.users.models import Membership

        self.org_a = Organization.objects.create(slug='cluba', name='Club A')
        self.org_b = Organization.objects.create(slug='clubb', name='Club B')

        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username='root', password='pass', email='root@test.com'
        )
        self.manager_a = User.objects.create_user(
            username='manager_a', password='pass', email='manager_a@test.com'
        )
        self.admin_a = User.objects.create_user(
            username='admin_a', password='pass', email='admin_a@test.com'
        )
        self.member_a = User.objects.create_user(
            username='member_a', password='pass', email='member_a@test.com'
        )
        self.manager_b = User.objects.create_user(
            username='manager_b', password='pass', email='manager_b@test.com'
        )
        Membership.objects.create(
            user=self.manager_a, organization=self.org_a, is_approved=True, role='manager'
        )
        Membership.objects.create(
            user=self.admin_a, organization=self.org_a, is_approved=True, role='admin'
        )
        Membership.objects.create(
            user=self.member_a, organization=self.org_a, is_approved=True, role='member'
        )
        Membership.objects.create(
            user=self.manager_b, organization=self.org_b, is_approved=True, role='manager'
        )
        # Un manager pendiente no debe recibir avisos
        self.pending_manager_a = User.objects.create_user(
            username='pending_manager_a', password='pass', email='pending_manager_a@test.com'
        )
        Membership.objects.create(
            user=self.pending_manager_a, organization=self.org_a,
            is_approved=False, role='manager',
        )

    def test_recipients_include_superusers_and_tenant_managers_only(self):
        recipients = get_moderation_recipients(self.org_a)
        self.assertCountEqual(
            recipients,
            ['root@test.com', 'manager_a@test.com', 'admin_a@test.com'],
        )

    def test_recipients_without_tenant_are_only_superusers(self):
        self.assertCountEqual(get_moderation_recipients(None), ['root@test.com'])


@override_settings(
    ALLOWED_HOSTS=['cluba.ilovevoley.es'],
    NOTIFICATION_EMAIL_ENABLED=True,
    EMAIL_HOST_USER='noreply@test.com',
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    EMAIL_NOTIFICATIONS={'new_user_pending': True},
)
class NewUserNotificationTest(TestCase):
    def setUp(self):
        from videosvoley.core.models import Organization
        from videosvoley.users.models import Membership

        self.org = Organization.objects.create(slug='cluba', name='Club A')

        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username='root', password='pass', email='root@test.com'
        )
        self.manager = User.objects.create_user(
            username='manager', password='pass', email='manager@test.com'
        )
        Membership.objects.create(
            user=self.manager, organization=self.org, is_approved=True, role='manager'
        )
        self.pending_user = User.objects.create_user(
            username='newbie', password='pass', is_approved=False
        )
        Membership.objects.create(
            user=self.pending_user, organization=self.org, is_approved=False
        )

    def _request(self):
        request = RequestFactory().get('/', HTTP_HOST='cluba.ilovevoley.es')
        request.tenant = self.org
        return request

    def test_notification_goes_to_tenant_moderators_with_panel_link(self):
        send_new_user_notification(self.pending_user, self._request())

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertCountEqual(email.to, ['root@test.com', 'manager@test.com'])
        html_body = email.alternatives[0][0]
        self.assertIn('/core/moderacion/', html_body)
        self.assertNotIn('/moderate/user/', html_body)


@override_settings(
    ALLOWED_HOSTS=['cluba.ilovevoley.es'],
    NOTIFICATION_EMAIL_ENABLED=True,
    EMAIL_HOST_USER='noreply@test.com',
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    EMAIL_NOTIFICATIONS={'new_user_pending': True},
)
class SignupNotificationTest(TestCase):
    """El alta avisa aunque no haya parent_info (caso OAuth auto-signup)."""

    def setUp(self):
        from django.core.cache import cache
        from videosvoley.core.models import Organization

        cache.clear()
        self.org = Organization.objects.create(slug='cluba', name='Club A')
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username='root', password='pass', email='root@test.com'
        )
        mail.outbox = []

    def test_signup_without_parent_info_notifies_admins(self):
        User = get_user_model()
        user = User.objects.create_user(
            username='oauth_user', password='pass', email='oauth@test.com'
        )
        request = RequestFactory().get('/', HTTP_HOST='cluba.ilovevoley.es')
        request.tenant = self.org

        user_signed_up.send(sender=User, request=request, user=user)

        self.assertEqual(len(mail.outbox), 1)
        self.assertCountEqual(mail.outbox[0].to, ['root@test.com'])

    def test_traditional_signup_sends_single_notification(self):
        response = self.client.post(
            '/accounts/signup/',
            {
                'username': 'trad',
                'email': 'trad@test.com',
                'password1': 'ComplexPass123!',
                'password2': 'ComplexPass123!',
                'parent_info': 'Padre de Pepito',
            },
            HTTP_HOST='cluba.ilovevoley.es',
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Nuevo usuario pendiente', mail.outbox[0].subject)



@override_settings(
    ALLOWED_HOSTS=['cluba.ilovevoley.es'],
    NOTIFICATION_EMAIL_ENABLED=True,
    EMAIL_HOST_USER='noreply@test.com',
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    EMAIL_NOTIFICATIONS={'new_user_pending': True},
)
class MembershipPendingNotificationTest(TestCase):
    def setUp(self):
        from videosvoley.core.models import Organization
        from videosvoley.users.models import Membership

        self.org = Organization.objects.create(slug='cluba', name='Club A')
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username='root', password='pass', email='root@test.com'
        )
        self.manager = User.objects.create_user(
            username='manager', password='pass', email='manager@test.com'
        )
        Membership.objects.create(
            user=self.manager, organization=self.org, is_approved=True, role='manager'
        )
        self.approved_user = User.objects.create_user(
            username='veteran', password='pass', email='veteran@test.com',
            is_approved=True,
        )
        mail.outbox = []

    def test_new_pending_membership_of_approved_user_notifies_moderators(self):
        from videosvoley.users.models import Membership

        Membership.objects.create(
            user=self.approved_user, organization=self.org, is_approved=False
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertCountEqual(mail.outbox[0].to, ['root@test.com', 'manager@test.com'])

    def test_signup_membership_of_pending_user_does_not_notify(self):
        from videosvoley.users.models import Membership

        User = get_user_model()
        new_user = User.objects.create_user(
            username='newbie', password='pass', email='newbie@test.com',
            is_approved=False,
        )
        Membership.objects.create(
            user=new_user, organization=self.org, is_approved=False
        )

        self.assertEqual(mail.outbox, [])

