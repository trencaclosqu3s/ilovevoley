import base64
import re
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from py_vapid import Vapid

from cryptography.hazmat.primitives.asymmetric import ec


class VapidConfigTest(TestCase):
    def test_generate_vapid_keys_command_outputs_keys(self):
        out = StringIO()
        call_command('generate_vapid_keys', stdout=out)
        output = out.getvalue()

        public_match = re.search(r'^VAPID_PUBLIC_KEY=(\S+)$', output, re.M)
        private_match = re.search(
            r'^VAPID_PRIVATE_KEY="(-----BEGIN PRIVATE KEY-----.*?-----END PRIVATE KEY-----)"$',
            output,
            re.M | re.S,
        )

        self.assertIsNotNone(public_match, 'El comando debe emitir VAPID_PUBLIC_KEY')
        self.assertIsNotNone(private_match, 'El comando debe emitir VAPID_PRIVATE_KEY en PEM')
        public_key = public_match.group(1)
        private_key = private_match.group(1)

        vapid = Vapid.from_pem(private_key.encode())
        raw_pub = base64.urlsafe_b64decode(public_key + '=' * (-len(public_key) % 4))
        self.assertEqual(len(raw_pub), 65)
        self.assertEqual(raw_pub[0], 0x04)

        public_number = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(), raw_pub
        )
        self.assertEqual(public_number.curve.name, 'secp256r1')
        self.assertEqual(
            public_number.public_numbers(),
            vapid.public_key.public_numbers(),
        )
