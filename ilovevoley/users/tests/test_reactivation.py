"""Reactivación a la carta de cuentas desactivadas por inactividad (#327).

El apagado masivo lo ejecuta la migración de datos 0025. Aquí se protege el
circuito que decide si una cuenta desactivada vuelve: la solicitud de la propia
persona, el aviso a los moderadores y la resolución (reactivar o descartar).
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ilovevoley.core.models import Organization
from ilovevoley.users.models import Membership

HOST = 'tenant-a.ilovevoley.es'

EMAIL_OVERRIDES = {
    'NOTIFICATION_EMAIL_ENABLED': True,
    'EMAIL_HOST_USER': 'noreply@test.com',
    'EMAIL_BACKEND': 'django.core.mail.backends.locmem.EmailBackend',
    'EMAIL_NOTIFICATIONS': {'new_user_pending': True},
    'CELERY_TASK_ALWAYS_EAGER': True,
    'CELERY_TASK_EAGER_PROPAGATES': True,
}

User = get_user_model()


@override_settings(**EMAIL_OVERRIDES)
class ReactivationRequestViewTests(TestCase):
    """La solicitud solo aplica a cuentas desactivadas aprobadas, es idempotente y avisa."""

    def setUp(self):
        mail.outbox = []
        self.user = User.objects.create_user(
            username='inactivo',
            email='inactivo@example.com',
            password='pass',
            is_approved=True,
            is_active=False,
        )
        User.objects.create_superuser(
            username='root', email='root@test.com', password='pass',
        )

    def test_inactive_approved_user_creates_request_and_notifies_moderators(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('request_reactivation'), {'login': 'inactivo'})

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.reactivation_requested_at)
        self.assertIn('root@test.com', [m.to[0] for m in mail.outbox])

    def test_active_user_gets_no_request(self):
        active = User.objects.create_user(
            username='activo', password='pass', is_approved=True, is_active=True,
        )
        self.client.post(reverse('request_reactivation'), {'login': 'activo'})
        active.refresh_from_db()
        self.assertIsNone(active.reactivation_requested_at)

    def test_rejected_user_cannot_request(self):
        rejected = User.objects.create_user(
            username='rechazado', password='pass', is_approved=False, is_active=False,
        )
        self.client.post(reverse('request_reactivation'), {'login': 'rechazado'})
        rejected.refresh_from_db()
        self.assertIsNone(rejected.reactivation_requested_at)

    def test_repeated_request_does_not_notify_again(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('request_reactivation'), {'login': 'inactivo'})
        mail.outbox = []

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('request_reactivation'), {'login': 'inactivo'})

        self.assertEqual(mail.outbox, [])


class LoginReactivationPromptTests(TestCase):
    """El login de una cuenta desactivada aprobada ofrece pedir la reactivación."""

    def test_inactive_approved_login_shows_reactivation_prompt(self):
        User.objects.create_user(
            username='inactivo', email='inactivo@example.com', password='pass',
            is_approved=True, is_active=False,
        )
        response = self.client.post(
            reverse('account_login'), {'login': 'inactivo', 'password': 'pass'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/reactivation_request.html')

    def test_rejected_user_login_keeps_generic_error(self):
        User.objects.create_user(
            username='rechazado', password='pass', is_approved=False, is_active=False,
        )
        response = self.client.post(
            reverse('account_login'), {'login': 'rechazado', 'password': 'pass'},
        )
        # La cuenta rechazada sigue el flujo genérico de allauth (redirección a
        # la página de cuenta inactiva), sin ofrecer la reactivación.
        self.assertTemplateNotUsed(response, 'users/reactivation_request.html')
        self.assertEqual(response.status_code, 302)


@override_settings(ALLOWED_HOSTS=[HOST])
class ModerationReactivationViewTests(TestCase):
    """El club resuelve las solicitudes de sus usuarios y no las de otros clubes."""

    def setUp(self):
        self.org = Organization.objects.create(slug='tenant-a', name='Tenant A')
        self.manager = User.objects.create_user(
            username='manager', password='pass', is_approved=True,
        )
        Membership.objects.create(
            user=self.manager, organization=self.org, role='manager', is_approved=True,
        )
        self.inactive = User.objects.create_user(
            username='inactivo', email='inactivo@example.com', password='pass',
            is_approved=True, is_active=False,
        )
        Membership.objects.create(
            user=self.inactive, organization=self.org, role='member', is_approved=True,
        )
        self.inactive.reactivation_requested_at = timezone.now()
        self.inactive.inactivity_warning_level = 2
        self.inactive.inactivity_warning_sent_at = timezone.now() - timedelta(days=5)
        self.inactive.save()
        self.client.force_login(self.manager)

    def test_manager_reactivates_user_in_their_club(self):
        response = self.client.post(
            reverse('core:reactivate_user_api', args=[self.inactive.id]), HTTP_HOST=HOST,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])

        self.inactive.refresh_from_db()
        self.assertTrue(self.inactive.is_active)
        self.assertIsNone(self.inactive.reactivation_requested_at)
        self.assertEqual(self.inactive.inactivity_warning_level, 0)

    def test_manager_dismisses_request_leaving_account_inactive(self):
        response = self.client.post(
            reverse('core:dismiss_reactivation_api', args=[self.inactive.id]), HTTP_HOST=HOST,
        )
        self.assertEqual(response.status_code, 200)

        self.inactive.refresh_from_db()
        self.assertFalse(self.inactive.is_active)
        self.assertIsNone(self.inactive.reactivation_requested_at)

    def test_non_moderator_cannot_reactivate(self):
        member = User.objects.create_user(
            username='socio', password='pass', is_approved=True,
        )
        Membership.objects.create(
            user=member, organization=self.org, role='member', is_approved=True,
        )
        self.client.force_login(member)

        response = self.client.post(
            reverse('core:reactivate_user_api', args=[self.inactive.id]), HTTP_HOST=HOST,
        )
        self.assertEqual(response.status_code, 403)
        self.inactive.refresh_from_db()
        self.assertFalse(self.inactive.is_active)

    def test_manager_cannot_reactivate_user_from_another_club(self):
        other_org = Organization.objects.create(slug='tenant-b', name='Tenant B')
        foreign = User.objects.create_user(
            username='ajeno', password='pass', is_approved=True, is_active=False,
        )
        Membership.objects.create(
            user=foreign, organization=other_org, role='member', is_approved=True,
        )
        foreign.reactivation_requested_at = timezone.now()
        foreign.save()

        response = self.client.post(
            reverse('core:reactivate_user_api', args=[foreign.id]), HTTP_HOST=HOST,
        )
        self.assertEqual(response.status_code, 404)
        foreign.refresh_from_db()
        self.assertFalse(foreign.is_active)

    def test_panel_lists_reactivation_requests(self):
        response = self.client.get(reverse('core:moderation_panel'), HTTP_HOST=HOST)
        self.assertIn(self.inactive, list(response.context['reactivation_users']))
