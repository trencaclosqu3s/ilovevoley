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

    def test_login_rate_limiting_by_ip_and_credential(self):
        login_url = reverse('account_login')
        client_ip = '198.51.100.30'

        # 5 intentos con la misma IP y la misma credencial
        for i in range(5):
            response = self.client.post(
                login_url,
                {'login': 'targeted_victim', 'password': 'wrongpassword'},
                REMOTE_ADDR=client_ip,
            )
            self.assertNotEqual(response.status_code, 429)

        # El 6º par (IP, credencial) se bloquea
        blocked_response = self.client.post(
            login_url,
            {'login': 'targeted_victim', 'password': 'wrongpassword'},
            REMOTE_ADDR=client_ip,
        )
        self.assertEqual(blocked_response.status_code, 429)

    def test_login_does_not_globally_lock_account_across_ips(self):
        """Decisión PR #200: la clave es IP+credencial, así que una cuenta no se
        bloquea globalmente con intentos distribuidos (se evita el DoS de cuenta)."""
        login_url = reverse('account_login')

        for i in range(5):
            response = self.client.post(
                login_url,
                {'login': 'targeted_victim', 'password': 'wrongpassword'},
                REMOTE_ADDR=f'198.51.100.{20 + i}',
            )
            self.assertNotEqual(response.status_code, 429)

        # Desde una IP nueva el intento no está bloqueado por la credencial ajena
        other_ip_response = self.client.post(
            login_url,
            {'login': 'targeted_victim', 'password': 'wrongpassword'},
            REMOTE_ADDR='198.51.100.99',
        )
        self.assertNotEqual(other_ip_response.status_code, 429)

    def test_empty_login_forms_do_not_share_bucket(self):
        """Formularios vacíos se discriminan por IP: envíos vacíos de varias IPs no
        consumen el mismo cubo ni bloquean a usuarios legítimos (PR #200)."""
        login_url = reverse('account_login')

        for i in range(5):
            response = self.client.post(
                login_url,
                {'login': '', 'password': ''},
                REMOTE_ADDR=f'203.0.113.{10 + i}',
            )
            self.assertNotEqual(response.status_code, 429)

        fresh_ip_response = self.client.post(
            login_url,
            {'login': '', 'password': ''},
            REMOTE_ADDR='203.0.113.99',
        )
        self.assertNotEqual(fresh_ip_response.status_code, 429)

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

    def test_password_reset_rate_limiting_by_ip_and_email(self):
        reset_url = reverse('account_reset_password')
        target_email = 'target_email@example.com'
        client_ip = '198.51.100.70'

        # 3 solicitudes para el mismo par (IP, email)
        for i in range(3):
            response = self.client.post(
                reset_url,
                {'email': target_email},
                REMOTE_ADDR=client_ip,
            )
            self.assertNotEqual(response.status_code, 429)

        # La 4ª solicitud del mismo par (IP, email) se bloquea
        blocked_response = self.client.post(
            reset_url,
            {'email': target_email},
            REMOTE_ADDR=client_ip,
        )
        self.assertEqual(blocked_response.status_code, 429)

    def test_password_reset_does_not_globally_lock_email_across_ips(self):
        """La clave IP+email evita que un atacante bloquee el reset de una víctima
        repartiendo peticiones desde muchas IPs (decisión PR #200)."""
        reset_url = reverse('account_reset_password')
        target_email = 'target_email@example.com'

        for i in range(3):
            response = self.client.post(
                reset_url,
                {'email': target_email},
                REMOTE_ADDR=f'198.51.100.{70 + i}',
            )
            self.assertNotEqual(response.status_code, 429)

        fresh_ip_response = self.client.post(
            reset_url,
            {'email': target_email},
            REMOTE_ADDR='198.51.100.80',
        )
        self.assertNotEqual(fresh_ip_response.status_code, 429)
