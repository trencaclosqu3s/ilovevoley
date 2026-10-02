import re
from pathlib import Path
from email.utils import parseaddr
from django.conf import settings
from django.test import SimpleTestCase


class OperationalSettingsTest(SimpleTestCase):
    """
    Verifica las directivas operativas de producción (Issue #121):
    - Pooling de conexiones y chequeo de salud en PostgreSQL.
    - Statement timeout para evitar queries colgadas.
    - Límite de subida alineado a 60MB en Django y Nginx.
    - Remitente institucional por defecto.
    """

    def test_database_connection_persistence_and_health_checks(self):
        """PostgreSQL debe tener CONN_MAX_AGE de 60s y chequeos de salud activos."""
        db_conf = settings.DATABASES['default']
        self.assertEqual(
            db_conf.get('CONN_MAX_AGE'), 60,
            "CONN_MAX_AGE debe ser 60 para pooling de conexiones persistentes.",
        )
        self.assertIs(
            db_conf.get('CONN_HEALTH_CHECKS'), True,
            "CONN_HEALTH_CHECKS debe ser True para verificar conexiones antes de reutilizarlas.",
        )

    def test_database_statement_timeout(self):
        """PostgreSQL OPTIONS debe definir statement_timeout de 30s."""
        db_conf = settings.DATABASES['default']
        options = db_conf.get('OPTIONS', {})
        cli_options = options.get('options', '')
        self.assertIn(
            'statement_timeout=30000', cli_options,
            "PostgreSQL OPTIONS debe incluir '-c statement_timeout=30000'.",
        )

    def test_upload_limits_configuration(self):
        """DATA_UPLOAD_MAX_MEMORY_SIZE debe permitir subidas en lote de hasta 60MB."""
        self.assertEqual(
            settings.DATA_UPLOAD_MAX_MEMORY_SIZE, 60 * 1024 * 1024,
            "DATA_UPLOAD_MAX_MEMORY_SIZE debe ser 60MB para subidas en lote.",
        )
        self.assertEqual(
            settings.FILE_UPLOAD_MAX_MEMORY_SIZE, 10 * 1024 * 1024,
            "FILE_UPLOAD_MAX_MEMORY_SIZE debe mantenerse en 10MB antes de pasar a disco.",
        )

    def test_institutional_sender_email(self):
        """DEFAULT_FROM_EMAIL y SERVER_EMAIL deben usar dirección institucional."""
        _, from_addr = parseaddr(settings.DEFAULT_FROM_EMAIL)
        _, server_addr = parseaddr(settings.SERVER_EMAIL)

        self.assertTrue(
            from_addr.endswith('@ilovevoley.es'),
            f"DEFAULT_FROM_EMAIL ({from_addr}) debe pertenecer al dominio @ilovevoley.es.",
        )
        self.assertNotIn('gmail.com', from_addr)

        self.assertTrue(
            server_addr.endswith('@ilovevoley.es'),
            f"SERVER_EMAIL ({server_addr}) debe pertenecer al dominio @ilovevoley.es.",
        )
        self.assertNotIn('gmail.com', server_addr)

    def test_nginx_client_max_body_size(self):
        """nginx.conf debe limitar client_max_body_size a 60M en el bloque del sitio."""
        nginx_path = Path(settings.BASE_DIR) / 'nginx.conf'
        self.assertTrue(nginx_path.exists(), "nginx.conf no encontrado en la raíz del proyecto")

        content = nginx_path.read_text(encoding='utf-8')
        match = re.search(r'client_max_body_size\s+([0-9]+[kKmMgG]?);', content)
        self.assertIsNotNone(match, "client_max_body_size no encontrado en nginx.conf")
        self.assertEqual(
            match.group(1).upper(), '60M',
            "client_max_body_size en nginx.conf debe ser 60M para alinearse con Django.",
        )
