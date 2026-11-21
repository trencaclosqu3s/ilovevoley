import re
from pathlib import Path
from email.utils import parseaddr

from decouple import config as env_config
from django.conf import settings
from django.test import SimpleTestCase


class OperationalSettingsTest(SimpleTestCase):
    """
    Verifica las directivas operativas de producción (Issue #121):
    - Límite de subida de 60MB en Nginx.
    - Remitente institucional por defecto.
    """

    def test_institutional_sender_email(self):
        """El **default de código** del remitente es institucional (#121).

        El valor efectivo puede sobreescribirse con `DEFAULT_FROM_EMAIL` /
        `SERVER_EMAIL` en el entorno (p. ej. un gmail en desarrollo local), y
        eso es legítimo. Este test solo vigila el default de `config.settings`,
        que es el que se usa cuando no hay override: si alguien cambia el
        default por una dirección personal, aquí salta.
        """
        for var, effective in (
            ('DEFAULT_FROM_EMAIL', settings.DEFAULT_FROM_EMAIL),
            ('SERVER_EMAIL', settings.SERVER_EMAIL),
        ):
            if env_config(var, default=None) is not None:
                continue  # override explícito del entorno: no es el default

            _, addr = parseaddr(effective)
            self.assertTrue(
                addr.endswith('@ilovevoley.es'),
                f"{var} ({addr}) debe pertenecer al dominio @ilovevoley.es.",
            )
            self.assertNotIn('gmail.com', addr)

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
