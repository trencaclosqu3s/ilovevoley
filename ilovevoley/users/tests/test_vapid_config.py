from io import StringIO
from django.core.management import call_command
from django.test import TestCase
from django.conf import settings


class VapidConfigTest(TestCase):
    def test_vapid_settings_exist(self):
        self.assertTrue(hasattr(settings, 'VAPID_PUBLIC_KEY'))
        self.assertTrue(hasattr(settings, 'VAPID_PRIVATE_KEY'))
        self.assertTrue(hasattr(settings, 'VAPID_CLAIMS_SUB'))

    def test_generate_vapid_keys_command_outputs_keys(self):
        out = StringIO()
        call_command('generate_vapid_keys', stdout=out)
        output = out.getvalue()
        self.assertIn('VAPID_PUBLIC_KEY=', output)
        self.assertIn('VAPID_PRIVATE_KEY=', output)
