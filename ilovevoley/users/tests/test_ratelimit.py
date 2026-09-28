from django.contrib.auth import get_user_model
from django.core import mail
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


@override_settings(
    RATELIMIT_ENABLE=True,
    RATELIMIT_USE_CACHE='default',
    AUTH_GLOBAL_LOGIN_FAILURE_THRESHOLD=3,
    AUTH_GLOBAL_RESET_THRESHOLD=3,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class GlobalAuthThresholdTests(TestCase):
    """Complemento de fuerza bruta distribuida (#202): umbral global por
    credencial sobre intentos fallidos, sin reabrir el DoS de cuenta."""

    def setUp(self):
        cache.clear()

    def test_login_distributed_few_attempts_not_globally_blocked(self):
        login_url = reverse('account_login')

        # 3 fallos desde 3 IPs = umbral exacto: nadie bloqueado globalmente.
        for i in range(3):
            response = self.client.post(
                login_url,
                {'login': 'targeted_victim', 'password': 'wrongpassword'},
                REMOTE_ADDR=f'198.51.100.{101 + i}',
            )
            self.assertNotEqual(response.status_code, 429)

        # El 4º fallo, aunque venga de una IP nueva, supera el umbral global.
        blocked_response = self.client.post(
            login_url,
            {'login': 'targeted_victim', 'password': 'wrongpassword'},
            REMOTE_ADDR='198.51.100.104',
        )
        self.assertEqual(blocked_response.status_code, 429)

    def test_login_correct_password_bypasses_global_threshold(self):
        """Un tercero no puede dejar sin acceso a la cuenta: el login correcto
        siempre pasa y resetea el contador global de fallos."""
        User = get_user_model()
        User.objects.create_user(
            username='targeted_victim',
            email='targeted_victim@example.com',
            password='correctpassword',
        )
        login_url = reverse('account_login')

        # Saturar el contador global de fallos desde varias IPs.
        for i in range(4):
            self.client.post(
                login_url,
                {'login': 'targeted_victim', 'password': 'wrongpassword'},
                REMOTE_ADDR=f'198.51.100.{110 + i}',
            )

        # Confirmar que el contador está bloqueando de verdad: un fallo extra
        # desde una IP nueva ya recibe 429 (si no, el test pasaría por no haber
        # superado nunca el umbral).
        throttled = self.client.post(
            login_url,
            {'login': 'targeted_victim', 'password': 'wrongpassword'},
            REMOTE_ADDR='198.51.100.119',
        )
        self.assertEqual(throttled.status_code, 429)

        # El login correcto desde una IP nueva no se bloquea.
        success = self.client.post(
            login_url,
            {'login': 'targeted_victim', 'password': 'correctpassword'},
            REMOTE_ADDR='198.51.100.120',
        )
        self.assertNotEqual(success.status_code, 429)

        # Y el contador quedó a cero: un fallo posterior vuelve a contar desde 1.
        after_reset = self.client.post(
            login_url,
            {'login': 'targeted_victim', 'password': 'wrongpassword'},
            REMOTE_ADDR='198.51.100.121',
        )
        self.assertNotEqual(after_reset.status_code, 429)

    def test_password_reset_global_threshold_stops_distributed_flood(self):
        User = get_user_model()
        User.objects.create_user(
            username='targeted_victim',
            email='targeted_victim@example.com',
            password='correctpassword',
        )
        reset_url = reverse('account_reset_password')
        target_email = 'targeted_victim@example.com'

        for i in range(3):
            response = self.client.post(
                reset_url,
                {'email': target_email},
                REMOTE_ADDR=f'198.51.100.{130 + i}',
            )
            self.assertNotEqual(response.status_code, 429)

        emails_sent = len(mail.outbox)
        self.assertEqual(emails_sent, 3, "cada solicitud válida envía un email")

        blocked_response = self.client.post(
            reset_url,
            {'email': target_email},
            REMOTE_ADDR='198.51.100.140',
        )
        self.assertEqual(blocked_response.status_code, 429)
        # La petición bloqueada no debe enviar el email: la comprobación del
        # umbral precede al form_valid de allauth.
        self.assertEqual(len(mail.outbox), emails_sent)
