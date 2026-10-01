from cryptography.hazmat.primitives import serialization
from django.core.management.base import BaseCommand
from py_vapid import Vapid, b64urlencode


class Command(BaseCommand):
    help = 'Genera un nuevo par de claves criptográficas VAPID (P-256) para Web Push'

    def handle(self, *args, **options):
        vapid = Vapid()
        vapid.generate_keys()

        # py-vapid expone la clave privada en formato PEM y convertimos la pública a raw URL-safe base64
        private_key = vapid.private_pem().decode('utf-8').strip()
        raw_pub = vapid.public_key.public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
        public_key = b64urlencode(raw_pub)

        self.stdout.write(self.style.SUCCESS('--- Claves VAPID Generadas ---'))
        self.stdout.write(f'VAPID_PUBLIC_KEY={public_key}')
        self.stdout.write(f'VAPID_PRIVATE_KEY="{private_key}"')
        self.stdout.write('VAPID_CLAIMS_SUB=mailto:admin@ilovevoley.es')
