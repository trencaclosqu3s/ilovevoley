from io import BytesIO
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core import mail
from unittest.mock import patch
from PIL import Image as PILImage

from ilovevoley.core.models import Organization
from ilovevoley.users.models import Membership
from ilovevoley.content.models import Image
from ilovevoley.core.moderation_views import (
    generate_moderation_token,
    verify_moderation_token,
    TOKEN_MAX_AGE,
    MODERATION_SALT,
)


@override_settings(
    ALLOWED_HOSTS=['ilovevoley.es', 'club1.ilovevoley.es', 'club2.ilovevoley.es', 'localhost', 'testserver'],
    TENANT_BASE_DOMAIN='ilovevoley.es',
    NOTIFICATION_EMAIL_ENABLED=True,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    EMAIL_HOST_USER='noreply@ilovevoley.es',
    EMAIL_NOTIFICATIONS={'image_pending': True, 'image_moderated': True, 'user_approved': True},
)
class ModerationViewsSecurityTest(TestCase):
    def setUp(self):
        cache.clear()
        mail.outbox.clear()
        User = get_user_model()

        # Organizations
        self.org1 = Organization.objects.create(slug='club1', name='Club Uno', is_active=True)
        self.org2 = Organization.objects.create(slug='club2', name='Club Dos', is_active=True)

        # Users
        self.superuser = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='password123'
        )
        self.manager_org1 = User.objects.create_user(
            username='manager1', email='manager1@test.com', password='password123', is_approved=True
        )
        Membership.objects.create(
            user=self.manager_org1, organization=self.org1, role='manager', is_approved=True
        )

        self.manager_org2 = User.objects.create_user(
            username='manager2', email='manager2@test.com', password='password123', is_approved=True
        )
        Membership.objects.create(
            user=self.manager_org2, organization=self.org2, role='manager', is_approved=True
        )

        self.regular_user = User.objects.create_user(
            username='regular', email='regular@test.com', password='password123', is_approved=True
        )
        Membership.objects.create(
            user=self.regular_user, organization=self.org1, role='member', is_approved=True
        )

        # Pending user to be moderated
        self.pending_user = User.objects.create_user(
            username='pending_user', email='pending@test.com', password='password123', is_approved=False
        )
        self.membership_org1 = Membership.objects.create(
            user=self.pending_user, organization=self.org1, role='member', is_approved=False
        )
        self.membership_org2 = Membership.objects.create(
            user=self.pending_user, organization=self.org2, role='member', is_approved=False
        )

        # Pending image to be moderated
        buf = BytesIO()
        PILImage.new('RGB', (10, 10), color='green').save(buf, format='JPEG')
        buf.seek(0)
        test_file = SimpleUploadedFile("test.jpg", buf.read(), content_type="image/jpeg")
        self.pending_image = Image.objects.create(
            title="Test Pending Image",
            image=test_file,
            uploaded_by=self.regular_user,
            organization=self.org1,
            status='pending'
        )
        mail.outbox.clear()  # Clear signals email from setup

    def test_token_uses_salt_and_tenant(self):
        token = generate_moderation_token('user', self.pending_user.id, 'approve', tenant_id=self.org1.id)
        data = verify_moderation_token(token)
        self.assertIsNotNone(data)
        self.assertEqual(data.item_type, 'user')
        self.assertEqual(data.item_id, self.pending_user.id)
        self.assertEqual(data.action, 'approve')
        self.assertEqual(data.tenant_id, self.org1.id)
        self.assertTrue(bool(data.nonce))
        self.assertEqual(MODERATION_SALT, "ilovevoley.moderation.v1")

    def test_token_max_age_is_between_30_and_60_minutes(self):
        self.assertGreaterEqual(TOKEN_MAX_AGE, 1800)
        self.assertLessEqual(TOKEN_MAX_AGE, 3600)

    def test_anonymous_get_redirects_to_login(self):
        token = generate_moderation_token('user', self.pending_user.id, 'approve', tenant_id=self.org1.id)
        url = reverse('moderate_user', kwargs={'token': token})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_get_does_not_mutate_user_state(self):
        self.client.force_login(self.manager_org1)
        token = generate_moderation_token('user', self.pending_user.id, 'approve', tenant_id=self.org1.id)
        url = reverse('moderate_user', kwargs={'token': token})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Confirmar')
        self.pending_user.refresh_from_db()
        self.membership_org1.refresh_from_db()
        self.assertFalse(self.pending_user.is_approved)
        self.assertFalse(self.membership_org1.is_approved)

    def test_get_does_not_mutate_image_state(self):
        self.client.force_login(self.manager_org1)
        token = generate_moderation_token('image', self.pending_image.id, 'approve', tenant_id=self.org1.id)
        url = reverse('moderate_image', kwargs={'token': token})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Confirmar')
        self.assertIn('image_data_uri', response.context)
        self.assertTrue(response.context['image_data_uri'].startswith('data:image/'))
        self.assertContains(response, response.context['image_data_uri'])
        self.pending_image.refresh_from_db()
        self.assertEqual(self.pending_image.status, 'pending')

    def test_unauthorized_user_forbidden(self):
        # Manager of org2 cannot moderate org1 resource
        self.client.force_login(self.manager_org2)
        token = generate_moderation_token('user', self.pending_user.id, 'approve', tenant_id=self.org1.id)
        url = reverse('moderate_user', kwargs={'token': token})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

        response_post = self.client.post(url)
        self.assertEqual(response_post.status_code, 403)

    def test_post_approves_user_scoped_to_tenant(self):
        self.client.force_login(self.manager_org1)
        token = generate_moderation_token('user', self.pending_user.id, 'approve', tenant_id=self.org1.id)
        url = reverse('moderate_user', kwargs={'token': token})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        self.pending_user.refresh_from_db()
        self.membership_org1.refresh_from_db()
        self.membership_org2.refresh_from_db()

        self.assertTrue(self.pending_user.is_approved)
        self.assertTrue(self.membership_org1.is_approved)
        # Org2 membership MUST remain unapproved
        self.assertFalse(self.membership_org2.is_approved)

    def test_post_rejects_user_scoped_to_tenant(self):
        self.client.force_login(self.manager_org1)
        token = generate_moderation_token('user', self.pending_user.id, 'reject', tenant_id=self.org1.id)
        url = reverse('moderate_user', kwargs={'token': token})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        # Org1 membership should be deleted by reject_user_membership
        self.assertFalse(
            Membership.objects.filter(user=self.pending_user, organization=self.org1).exists()
        )
        # Org2 membership MUST remain untouched
        self.assertTrue(
            Membership.objects.filter(user=self.pending_user, organization=self.org2).exists()
        )

    def test_post_approves_image_with_authenticated_moderator(self):
        self.client.force_login(self.manager_org1)
        token = generate_moderation_token('image', self.pending_image.id, 'approve', tenant_id=self.org1.id)
        url = reverse('moderate_image', kwargs={'token': token})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn('image_data_uri', response.context)
        self.assertTrue(response.context['image_data_uri'].startswith('data:image/'))
        self.assertContains(response, response.context['image_data_uri'])
        self.pending_image.refresh_from_db()
        self.assertEqual(self.pending_image.status, 'approved')
        self.assertEqual(self.pending_image.moderated_by, self.manager_org1)

    def test_post_rejects_image_with_authenticated_moderator(self):
        self.client.force_login(self.manager_org1)
        token = generate_moderation_token('image', self.pending_image.id, 'reject', tenant_id=self.org1.id)
        url = reverse('moderate_image', kwargs={'token': token})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        self.pending_image.refresh_from_db()
        self.assertEqual(self.pending_image.status, 'rejected')
        self.assertEqual(self.pending_image.moderated_by, self.manager_org1)

    def test_token_cannot_be_reused(self):
        self.client.force_login(self.manager_org1)
        token = generate_moderation_token('user', self.pending_user.id, 'approve', tenant_id=self.org1.id)
        url = reverse('moderate_user', kwargs={'token': token})

        # First POST succeeds
        resp1 = self.client.post(url)
        self.assertEqual(resp1.status_code, 200)

        # Second POST with same token must fail
        resp2 = self.client.post(url)
        self.assertEqual(resp2.status_code, 400)
        self.assertContains(resp2, 'ya ha sido utilizado', status_code=400)

    def test_expired_token_rejected(self):
        self.client.force_login(self.superuser)
        token = generate_moderation_token('user', self.pending_user.id, 'approve', tenant_id=self.org1.id)
        url = reverse('moderate_user', kwargs={'token': token})

        # Expire token
        with patch('ilovevoley.core.moderation_views.TOKEN_MAX_AGE', -1):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 400)

    def test_inactive_tenant_token_does_not_approve_globally(self):
        self.org1.is_active = False
        self.org1.save(update_fields=['is_active'])
        self.client.force_login(self.superuser)
        token = generate_moderation_token(
            'user', self.pending_user.id, 'approve', tenant_id=self.org1.id
        )
        url = reverse('moderate_user', kwargs={'token': token})

        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'desactivada', status_code=400)

        self.membership_org1.refresh_from_db()
        self.membership_org2.refresh_from_db()
        self.pending_user.refresh_from_db()
        self.assertFalse(self.membership_org1.is_approved)
        self.assertFalse(self.membership_org2.is_approved)
        self.assertFalse(self.pending_user.is_approved)

    def test_image_uploaded_signal_generates_absolute_urls_and_scoped_recipients(self):
        buf = BytesIO()
        PILImage.new('RGB', (10, 10), color='green').save(buf, format='JPEG')
        buf.seek(0)
        test_file = SimpleUploadedFile("signal_test.jpg", buf.read(), content_type="image/jpeg")
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            Image.objects.create(
                title="Signal Test Image",
                image=test_file,
                uploaded_by=self.regular_user,
                organization=self.org1,
                status='pending'
            )

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        # Must be sent to superuser and org1 manager, but NOT org2 manager
        self.assertIn(self.superuser.email, email.to)
        self.assertIn(self.manager_org1.email, email.to)
        self.assertNotIn(self.manager_org2.email, email.to)

        html_body = email.alternatives[0][0]
        # URLs must be absolute with tenant domain
        self.assertTrue(
            'https://club1.ilovevoley.es/moderate/image/' in html_body
            or 'http://club1.ilovevoley.es/moderate/image/' in html_body
        )
        self.assertNotIn('href="/moderate/image/', html_body)

