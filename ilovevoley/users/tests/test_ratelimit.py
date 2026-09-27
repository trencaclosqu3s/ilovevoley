from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(
    RATELIMIT_ENABLE=True,
    RATELIMIT_USE_CACHE='default',
)
class AuthRateLimitingTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_login_rate_limiting_by_ip(self):
        login_url = reverse('account_login')
        client_ip = '198.51.100.10'

        # Primeros 5 intentos dentro del límite
        for i in range(5):
            response = self.client.post(
                login_url,
                {'login': f'user_{i}', 'password': 'wrongpassword'},
                REMOTE_ADDR=client_ip,
            )
            self.assertNotEqual(
                response.status_code,
                429,
                f"El intento {i+1} no debería ser bloqueado",
            )

        # El 6º intento desde la misma IP debe ser bloqueado con 429
        blocked_response = self.client.post(
            login_url,
            {'login': 'user_blocked', 'password': 'wrongpassword'},
            REMOTE_ADDR=client_ip,
        )
        self.assertEqual(blocked_response.status_code, 429)
        self.assertIn('Tiempo de descanso'.encode('utf-8'), blocked_response.content)

    def test_login_rate_limiting_by_credential(self):
        login_url = reverse('account_login')
        target_username = 'targeted_victim'

        # 5 intentos con el mismo usuario desde IPs distintas
        for i in range(5):
            response = self.client.post(
                login_url,
                {'login': target_username, 'password': 'wrongpassword'},
                REMOTE_ADDR=f'198.51.100.{20 + i}',
            )
            self.assertNotEqual(response.status_code, 429)

        # El 6º intento con el mismo usuario (incluso desde otra IP) debe recibir 429
        blocked_response = self.client.post(
            login_url,
            {'login': target_username, 'password': 'wrongpassword'},
            REMOTE_ADDR='198.51.100.99',
        )
        self.assertEqual(blocked_response.status_code, 429)

        # Pero otro usuario desde una IP nueva debe poder intentar
        other_response = self.client.post(
            login_url,
            {'login': 'other_user', 'password': 'wrongpassword'},
            REMOTE_ADDR='198.51.100.100',
        )
        self.assertNotEqual(other_response.status_code, 429)

    def test_signup_rate_limiting_by_ip(self):
        signup_url = reverse('account_signup')
        client_ip = '198.51.100.50'

        # Límite configurado: 3/minuto
        for i in range(3):
            response = self.client.post(
                signup_url,
                {'email': f'test{i}@example.com'},
                REMOTE_ADDR=client_ip,
            )
            self.assertNotEqual(response.status_code, 429)

        # 4º intento bloqueado
        blocked_response = self.client.post(
            signup_url,
            {'email': 'test_blocked@example.com'},
            REMOTE_ADDR=client_ip,
        )
        self.assertEqual(blocked_response.status_code, 429)

    def test_password_reset_rate_limiting_by_ip(self):
        reset_url = reverse('account_reset_password')
        client_ip = '198.51.100.60'

        # Límite configurado: 3/minuto
        for i in range(3):
            response = self.client.post(
                reset_url,
                {'email': f'user{i}@example.com'},
                REMOTE_ADDR=client_ip,
            )
            self.assertNotEqual(response.status_code, 429)

        # 4º intento bloqueado
        blocked_response = self.client.post(
            reset_url,
            {'email': 'user_blocked@example.com'},
            REMOTE_ADDR=client_ip,
        )
        self.assertEqual(blocked_response.status_code, 429)

    def test_password_reset_rate_limiting_by_email(self):
        reset_url = reverse('account_reset_password')
        target_email = 'target_email@example.com'

        # Límite configurado: 3/minuto para el mismo email
        for i in range(3):
            response = self.client.post(
                reset_url,
                {'email': target_email},
                REMOTE_ADDR=f'198.51.100.{70 + i}',
            )
            self.assertNotEqual(response.status_code, 429)

        # 4º intento con el mismo email bloqueado
        blocked_response = self.client.post(
            reset_url,
            {'email': target_email},
            REMOTE_ADDR='198.51.100.80',
        )
        self.assertEqual(blocked_response.status_code, 429)
