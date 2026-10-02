from django.test import TestCase, RequestFactory, override_settings
from django.contrib.auth import get_user_model
from django.contrib.admin.sites import AdminSite
from django.core import mail
from django.contrib.messages.storage.fallback import FallbackStorage
from ilovevoley.core.email_utils import send_admin_email_to_users
from ilovevoley.users.admin import UserAdmin, WebPushAuditAdmin
from ilovevoley.users.models import WebPushAudit

User = get_user_model()

CELERY_EAGER = {
    'CELERY_TASK_ALWAYS_EAGER': True,
    'CELERY_TASK_EAGER_PROPAGATES': True,
}

class AdminEmailUtilsTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username='admin_test',
            email='admin@example.com',
            first_name='Admin',
            last_name='Voley',
            password='password123'
        )
        self.user1 = User.objects.create_user(
            username='user1',
            email='user1@example.com',
            first_name='Carlos',
            last_name='Gómez',
            password='password123'
        )
        self.user_no_email = User.objects.create_user(
            username='user_no_email',
            email='',
            first_name='Sin',
            last_name='Email',
            password='password123'
        )

    def test_send_admin_email_single_user(self):
        """Prueba envío a un usuario individual"""
        mail.outbox = []
        result = send_admin_email_to_users(
            subject='Prueba Asunto',
            message_body='Hola este es un mensaje de prueba.',
            recipients=[self.user1],
            admin_user=self.admin_user,
            send_copy=False
        )

        self.assertEqual(result['sent_count'], 1)
        self.assertEqual(result['failed_count'], 0)
        self.assertEqual(result['skipped_no_email_count'], 0)
        self.assertEqual(len(mail.outbox), 1)

        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.to, ['user1@example.com'])
        self.assertEqual(sent_email.subject, 'Prueba Asunto')
        self.assertIn('Carlos Gómez', sent_email.body)
        self.assertIn('Hola este es un mensaje de prueba.', sent_email.body)
        self.assertIn('Admin Voley', sent_email.body)
        self.assertEqual(sent_email.reply_to, ['Admin Voley <admin@example.com>'])

        # Verificar contenido HTML adjunto
        self.assertEqual(len(sent_email.alternatives), 1)
        html_content, mimetype = sent_email.alternatives[0]
        self.assertEqual(mimetype, 'text/html')
        self.assertIn('Carlos Gómez', html_content)
        self.assertIn('Hola este es un mensaje de prueba.', html_content)

    def test_send_admin_email_with_copy(self):
        """Prueba que send_copy=True envía una copia al administrador"""
        mail.outbox = []
        result = send_admin_email_to_users(
            subject='Aviso de Entrenamiento',
            message_body='Cambio de horario.',
            recipients=[self.user1],
            admin_user=self.admin_user,
            send_copy=True
        )

        self.assertEqual(result['sent_count'], 1)
        self.assertEqual(len(mail.outbox), 2)

        # Primer correo: al usuario
        self.assertEqual(mail.outbox[0].to, ['user1@example.com'])
        # Segundo correo: copia al admin
        copy_email = mail.outbox[1]
        self.assertEqual(copy_email.to, ['admin@example.com'])
        self.assertEqual(copy_email.subject, '[Copia] Aviso de Entrenamiento')
        self.assertIn('user1@example.com', copy_email.body)

    def test_send_admin_email_skips_user_without_email(self):
        """Prueba que los usuarios sin email son omitidos correctamente"""
        mail.outbox = []
        result = send_admin_email_to_users(
            subject='Aviso general',
            message_body='Contenido.',
            recipients=[self.user1, self.user_no_email],
            admin_user=self.admin_user,
            send_copy=False
        )

        self.assertEqual(result['sent_count'], 1)
        self.assertEqual(result['skipped_no_email_count'], 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['user1@example.com'])


class UserAdminEmailActionTests(TestCase):
    def setUp(self):
        self.site = AdminSite()
        self.admin = UserAdmin(User, self.site)
        self.factory = RequestFactory()

        self.admin_user = User.objects.create_superuser(
            username='admin_staff',
            email='admin@ilovevoley.com',
            first_name='Admin',
            last_name='Staff',
            password='password123'
        )
        self.user1 = User.objects.create_user(
            username='carlos',
            email='carlos@example.com',
            first_name='Carlos',
            last_name='Ruiz',
            password='password123'
        )
        self.user_no_email = User.objects.create_user(
            username='sin_correo',
            email='',
            first_name='Sin',
            last_name='Correo',
            password='password123'
        )

    def _setup_request(self, request):
        request.user = self.admin_user
        setattr(request, 'session', {})
        setattr(request, '_messages', FallbackStorage(request))

    def test_bulk_action_get_form(self):
        """Prueba que la acción masiva muestra el formulario intermedio y
        separa destinatarios con correo de los que no lo tienen."""
        self.client.force_login(self.admin_user)
        response = self.client.post('/admin/users/user/', {
            'action': 'send_email_action',
            '_selected_action': [str(self.user1.pk), str(self.user_no_email.pk)],
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['users_with_email']), [self.user1])
        self.assertEqual(list(response.context['users_without_email']), [self.user_no_email])

    @override_settings(**CELERY_EAGER)
    def test_bulk_action_post_send_success(self):
        """Prueba el envío exitoso desde la acción masiva"""
        mail.outbox = []
        request = self.factory.post('/admin/users/user/', {
            'action': 'send_email_action',
            '_selected_action': [str(self.user1.pk)],
            'apply': 'yes',
            'subject': 'Mensaje masivo de prueba',
            'message': 'Cuerpo del mensaje masivo.',
            'send_copy': '1',
        })
        self._setup_request(request)

        qs = User.objects.filter(pk=self.user1.pk)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.admin.send_email_action(request, qs)

        # Retorna None para que Django redirija al changelist
        self.assertIsNone(response)
        self.assertEqual(len(mail.outbox), 2)  # 1 usuario + 1 copia admin
        self.assertEqual(mail.outbox[0].to, ['carlos@example.com'])
        self.assertEqual(mail.outbox[0].subject, 'Mensaje masivo de prueba')

    def test_detail_action_get_form(self):
        """Prueba que la acción de detalle muestra el formulario intermedio con
        el usuario como único destinatario y marcado como no masivo."""
        self.client.force_login(self.admin_user)
        response = self.client.get(
            f'/admin/users/user/{self.user1.pk}/send_email_detail_action/'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['users_with_email']), [self.user1])
        self.assertFalse(response.context['is_bulk'])

    @override_settings(**CELERY_EAGER)
    def test_detail_action_post_success(self):
        """Prueba el envío exitoso desde la acción de detalle"""
        mail.outbox = []
        request = self.factory.post(f'/admin/users/user/{self.user1.pk}/send_email_detail_action/', {
            'apply': 'yes',
            'subject': 'Aviso individual',
            'message': 'Mensaje individual directo.',
        })
        self._setup_request(request)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.admin.send_email_detail_action(request, self.user1.pk)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['carlos@example.com'])
        self.assertEqual(mail.outbox[0].subject, 'Aviso individual')


class WebPushAuditAdminTest(TestCase):
    """Verifica que el admin de WebPushAudit sea de solo lectura y permita cascade delete (#316)."""

    def setUp(self):
        self.site = AdminSite()
        self.model_admin = WebPushAuditAdmin(WebPushAudit, self.site)
        self.factory = RequestFactory()
        self.superuser = User.objects.create_superuser(
            username='admin_audit',
            email='audit@example.com',
            password='password123',
        )
        self.staff_user = User.objects.create_user(
            username='staff_audit',
            email='staff@example.com',
            is_staff=True,
            password='password123',
        )

    def test_admin_is_read_only_and_allows_superuser_delete(self):
        request_staff = self.factory.get('/admin/users/webpushaudit/')
        request_staff.user = self.staff_user

        self.assertFalse(self.model_admin.has_add_permission(request_staff))
        self.assertFalse(self.model_admin.has_change_permission(request_staff))
        self.assertFalse(self.model_admin.has_delete_permission(request_staff))

        request_admin = self.factory.get('/admin/users/webpushaudit/')
        request_admin.user = self.superuser
        self.assertFalse(self.model_admin.has_add_permission(request_admin))
        self.assertFalse(self.model_admin.has_change_permission(request_admin))
        self.assertTrue(self.model_admin.has_delete_permission(request_admin))
