import re
from pathlib import Path

from django.conf import settings
from django.test import Client, TestCase, override_settings


@override_settings(ALLOWED_HOSTS=['ilovevoley.es', '.ilovevoley.es', 'localhost', 'testserver'])
class PWATemplatesTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_base_template_wires_standalone_back_button(self):
        # El retroceso in-app solo funciona si el id del template coincide con
        # el que busca pwa_nav.js; un rename lo dejaría muerto en silencio.
        js_path = Path(settings.BASE_DIR, 'ilovevoley', 'static', 'js', 'pwa_nav.js')
        js = js_path.read_text(encoding='utf-8')
        match = re.search(r'getElementById\(["\']([\w-]+)["\']\)', js)
        self.assertIsNotNone(match, 'pwa_nav.js no busca el botón por id')
        button_id = match.group(1)

        response = self.client.get('/', HTTP_HOST='ilovevoley.es')
        content = response.content.decode('utf-8')

        self.assertIn(f'id="{button_id}"', content)
        self.assertIn('data-home-url=', content)

    def test_navbar_renders_club_switcher_only_with_multiple_memberships(self):
        from django.contrib.auth import get_user_model
        from ilovevoley.core.models import Organization
        from ilovevoley.users.models import Membership

        user = get_user_model().objects.create_user(username='switcher', password='testpassword123')
        org1 = Organization.objects.create(slug='clubalpha', name='Club Alpha', is_active=True)
        org2 = Organization.objects.create(slug='clubbeta', name='Club Beta', is_active=True)
        Membership.objects.create(user=user, organization=org1, is_approved=True)
        Membership.objects.create(user=user, organization=org2, is_approved=True)

        self.client.login(username='switcher', password='testpassword123')
        response = self.client.get('/profile/', HTTP_HOST='clubalpha.ilovevoley.es')
        content = response.content.decode('utf-8')

        self.assertIn('data-dropdown="club-switcher"', content)
        self.assertIn('Club Alpha', content)
        self.assertIn('Club Beta', content)

        # Con una sola membresía el conmutador no debe renderizarse.
        Membership.objects.filter(user=user, organization=org2).delete()
        single = self.client.get('/profile/', HTTP_HOST='clubalpha.ilovevoley.es')
        self.assertNotIn('data-dropdown="club-switcher"', single.content.decode('utf-8'))
