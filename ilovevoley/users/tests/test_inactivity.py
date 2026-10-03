from datetime import timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from ilovevoley.core.models import Organization
from ilovevoley.users.models import WebPushSubscription
from ilovevoley.users.tasks import process_inactive_users_task
from ilovevoley.users.tokens import generate_deactivation_token, verify_deactivation_token

User = get_user_model()


class InactivityTaskTests(TestCase):
    """Protege la regla de negocio del ciclo de vida y desactivación de usuarios inactivos (#327)."""

    def setUp(self):
        self.now = timezone.now()
        self.org = Organization.objects.create(name='Club Test', slug='club-test')

        # Usuario activo normal
        self.user_active = User.objects.create_user(
            username='user_active',
            email='active@example.com',
            password='password123',
            is_approved=True,
            is_active=True,
        )
        self.user_active.last_login = self.now - timedelta(days=10)
        self.user_active.save()

        # Usuario candidato a primer aviso (340 días inactivo)
        self.user_warn1 = User.objects.create_user(
            username='user_warn1',
            email='warn1@example.com',
            password='password123',
            is_approved=True,
            is_active=True,
        )
        self.user_warn1.last_login = self.now - timedelta(days=340)
        self.user_warn1.save()

        # Usuario candidato a aviso final (360 días inactivo, ya recibió el primer aviso hace 20 días)
        self.user_warn2 = User.objects.create_user(
            username='user_warn2',
            email='warn2@example.com',
            password='password123',
            is_approved=True,
            is_active=True,
            inactivity_warning_level=1,
            inactivity_warning_sent_at=self.now - timedelta(days=20),
        )
        self.user_warn2.last_login = self.now - timedelta(days=360)
        self.user_warn2.save()

        # Usuario candidato a desactivación (370 días inactivo, recibió aviso final hace 10 días)
        self.user_deact = User.objects.create_user(
            username='user_deact',
            email='deact@example.com',
            password='password123',
            is_approved=True,
            is_active=True,
            inactivity_warning_level=2,
            inactivity_warning_sent_at=self.now - timedelta(days=10),
        )
        self.user_deact.last_login = self.now - timedelta(days=370)
        self.user_deact.save()

        # Suscripción webpush para verificar su borrado en la desactivación
        WebPushSubscription.objects.create(
            user=self.user_deact,
            organization=self.org,
            endpoint='https://push.example.com/sub_deact',
            p256dh='key',
            auth='auth',
        )

        # Superusuario inactivo (debe excluirse siempre)
        self.superuser = User.objects.create_superuser(
            username='super_inactive',
            email='super@example.com',
            password='password123',
        )
        self.superuser.last_login = self.now - timedelta(days=400)
        self.superuser.save()

        # Staff inactivo (debe excluirse siempre)
        self.staff_user = User.objects.create_user(
            username='staff_inactive',
            email='staff@example.com',
            password='password123',
            is_staff=True,
            is_approved=True,
            is_active=True,
        )
        self.staff_user.last_login = self.now - timedelta(days=400)
        self.staff_user.save()

    @override_settings(NOTIFICATION_EMAIL_ENABLED=True, EMAIL_HOST_USER='test@example.com')
    def test_process_inactive_users_flow(self):
        """Verifica los 3 escalones: aviso 1, aviso urgente 2 y desactivación al vencer plazos."""
        mail.outbox = []

        result = process_inactive_users_task()

        self.assertEqual(result['first_warnings_sent'], 1)
        self.assertEqual(result['final_warnings_sent'], 1)
        self.assertEqual(result['deactivated_count'], 1)

        # 1. user_warn1 pasó a nivel 1
        self.user_warn1.refresh_from_db()
        self.assertEqual(self.user_warn1.inactivity_warning_level, 1)
        self.assertIsNotNone(self.user_warn1.inactivity_warning_sent_at)

        # 2. user_warn2 pasó a nivel 2
        self.user_warn2.refresh_from_db()
        self.assertEqual(self.user_warn2.inactivity_warning_level, 2)

        # 3. user_deact fue desactivado y su suscripción push eliminada
        self.user_deact.refresh_from_db()
        self.assertFalse(self.user_deact.is_active)
        self.assertFalse(WebPushSubscription.objects.filter(user=self.user_deact).exists())

        # 4. Superuser, staff y usuario activo no sufrieron cambios
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_active)
        self.assertEqual(self.superuser.inactivity_warning_level, 0)

        self.staff_user.refresh_from_db()
        self.assertTrue(self.staff_user.is_active)
        self.assertEqual(self.staff_user.inactivity_warning_level, 0)

        self.user_active.refresh_from_db()
        self.assertTrue(self.user_active.is_active)
        self.assertEqual(self.user_active.inactivity_warning_level, 0)

        # Comprobar que los correos salieron hacia los destinatarios adecuados
        recipient_emails = [m.to[0] for m in mail.outbox]
        self.assertIn('warn1@example.com', recipient_emails)
        self.assertIn('warn2@example.com', recipient_emails)
        self.assertNotIn('active@example.com', recipient_emails)
        self.assertNotIn('super@example.com', recipient_emails)
        self.assertNotIn('staff@example.com', recipient_emails)

    def test_login_resets_inactivity_warning(self):
        """Verifica que cuando un usuario con aviso pendiente inicia sesión, se resetea su contador."""
        user = User.objects.create_user(
            username='user_logging_in',
            email='login@example.com',
            password='password123',
            is_approved=True,
            is_active=True,
            inactivity_warning_level=2,
            inactivity_warning_sent_at=self.now - timedelta(days=5),
        )

        user_logged_in.send(sender=User, request=None, user=user)

        user.refresh_from_db()
        self.assertEqual(user.inactivity_warning_level, 0)
        self.assertIsNone(user.inactivity_warning_sent_at)


class DeactivateAccountViewTests(TestCase):
    """Verifica el flujo de auto-desactivación en 1 clic con token seguro (#327)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='test_deact',
            email='deact_test@example.com',
            password='password123',
            is_approved=True,
            is_active=True,
        )
        self.token = generate_deactivation_token(self.user)

    def test_verify_token_valid_and_invalid(self):
        """El token generado debe resolver al user_id y fallar si está manipulado."""
        self.assertEqual(verify_deactivation_token(self.token), self.user.id)
        self.assertIsNone(verify_deactivation_token('token_invalido'))
        self.assertIsNone(verify_deactivation_token(''))

    def test_get_shows_confirmation_without_deactivating(self):
        """Un GET (como el de bots o antivirus de email) NO desactiva la cuenta."""
        url = reverse('deactivate_account', args=[self.token])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/deactivate_account_confirm.html')
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_post_confirms_deactivation(self):
        """Un POST válido confirma y desactiva la cuenta inmediatamente."""
        url = reverse('deactivate_account', args=[self.token])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/deactivate_account_success.html')
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_invalid_token_returns_400(self):
        """Un token corrupto retorna 400."""
        url = reverse('deactivate_account', args=['token_falso_123'])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)
        self.assertTemplateUsed(response, 'users/deactivate_account_invalid.html')
