import re
from django.test import Client, TestCase, override_settings
from django.contrib.auth import get_user_model
from ilovevoley.core.models import Organization

User = get_user_model()


@override_settings(ALLOWED_HOSTS=['santjust.ilovevoley.es', 'localhost', 'testserver'])
class ProfileWebPushTemplateTest(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='CV Sant Just', slug='santjust')
        self.user = User.objects.create_user(
            username='socio',
            email='socio@test.es',
            password='password123',
            is_approved=True,
        )
        self.client = Client()

    def test_profile_page_contains_webpush_section(self):
        self.client.login(username='socio', password='password123')
        response = self.client.get('/profile/', HTTP_HOST='santjust.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        self.assertIn('Notificaciones Push', content)
        self.assertIn('webpush.js', content)
        self.assertIn('id="webpush-status-badge"', content)
        self.assertIn('data-call="toggleWebPush"', content)

    def test_base_template_renders_valid_csrf_token_meta(self):
        self.client.login(username='socio', password='password123')
        response = self.client.get('/profile/', HTTP_HOST='santjust.ilovevoley.es')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        match = re.search(r'<meta name="csrf-token" content="([^"]+)">', content)
        self.assertIsNotNone(match, 'Meta tag csrf-token no encontrado en el template base')
        token = match.group(1)
        self.assertTrue(len(token) >= 32, 'El token CSRF del meta tag debe ser válido')

