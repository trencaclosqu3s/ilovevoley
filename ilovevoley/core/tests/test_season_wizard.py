from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from ilovevoley.competitions.models import League
from ilovevoley.core.forms import SeasonWizardForm
from ilovevoley.core.models import Season
from ilovevoley.core.services.season_wizard import preview_season, start_season


class SeasonWizardServiceTest(TestCase):
    def setUp(self):
        self.old = Season.objects.create(
            name='2025-26', start_year=2025, end_year=2026, is_current=True
        )

    def test_start_season_creates_and_activates(self):
        summary = start_season('2026-27')

        new = Season.objects.get(name='2026-27')
        self.assertTrue(new.is_current)
        self.assertFalse(Season.objects.get(pk=self.old.pk).is_current)
        self.assertEqual(summary['season'], new)

    def test_start_season_is_idempotent(self):
        start_season('2026-27')
        start_season('2026-27')

        self.assertEqual(Season.objects.filter(name='2026-27').count(), 1)
        self.assertTrue(Season.objects.get(name='2026-27').is_current)

    def test_start_season_archives_outgoing_main_leagues(self):
        main = League.objects.create(
            name='Liga saliente', federation_id='F-MAIN',
            season=self.old, visibility_type='main', is_active=True,
        )
        external = League.objects.create(
            name='Liga externa', federation_id='F-EXT',
            season=self.old, visibility_type='external', is_active=True,
        )

        summary = start_season('2026-27')

        main.refresh_from_db()
        external.refresh_from_db()
        self.assertEqual(main.visibility_type, 'historical')
        self.assertTrue(main.is_historical)
        self.assertTrue(main.is_active, 'archivar no debe romper el detalle de liga')
        # Las que no eran 'main' no se tocan.
        self.assertEqual(external.visibility_type, 'external')
        self.assertFalse(external.is_historical)
        self.assertEqual(summary['archived_leagues'], 1)

    def test_preview_does_not_write(self):
        League.objects.create(
            name='Liga saliente', federation_id='F-MAIN',
            season=self.old, visibility_type='main', is_active=True,
        )

        summary = preview_season('2026-27')

        self.assertTrue(summary['valid'])
        self.assertTrue(summary['is_new'])
        self.assertFalse(summary['already_current'])
        self.assertEqual(summary['outgoing_season'], self.old)
        self.assertEqual(summary['leagues_to_archive'], 1)
        self.assertFalse(Season.objects.filter(name='2026-27').exists())

    def test_preview_invalid_name(self):
        summary = preview_season('temp')
        self.assertFalse(summary['valid'])


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost'])
class SeasonWizardViewTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username='root', password='pass', email='root@test.com'
        )
        self.member = User.objects.create_user(username='member', password='pass')
        self.wizard_url = reverse('core:season_wizard')
        self.confirm_url = reverse('core:season_wizard_confirm')

    def test_non_superuser_forbidden(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(self.wizard_url).status_code, 403)
        self.assertEqual(
            self.client.get(self.confirm_url, {'name': '2026-27'}).status_code, 403
        )

    def test_superuser_gets_form(self):
        self.client.force_login(self.superuser)
        response = self.client.get(self.wizard_url)
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.context['form'], SeasonWizardForm)
        self.assertIn('name', response.context['form'].fields)

    def test_post_valid_redirects_to_confirm(self):
        self.client.force_login(self.superuser)
        response = self.client.post(self.wizard_url, {'name': '2026-27'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f'{self.confirm_url}?name=2026-27')

    def test_post_invalid_rerenders_with_error(self):
        self.client.force_login(self.superuser)
        response = self.client.post(self.wizard_url, {'name': 'temp'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('name', response.context['form'].errors)

    def test_confirm_get_shows_summary(self):
        self.client.force_login(self.superuser)
        response = self.client.get(self.confirm_url, {'name': '2026-27'})
        self.assertEqual(response.status_code, 200)

        summary = response.context['summary']
        self.assertEqual(summary['name'], '2026-27')
        self.assertEqual(summary['start_year'], 2026)
        self.assertEqual(summary['end_year'], 2027)
        self.assertTrue(summary['is_new'])

    def test_confirm_post_activates_season(self):
        Season.objects.create(
            name='2025-26', start_year=2025, end_year=2026, is_current=True
        )
        self.client.force_login(self.superuser)

        response = self.client.post(self.confirm_url, {'name': '2026-27'})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.wizard_url)
        self.assertTrue(Season.objects.get(name='2026-27').is_current)

    def test_confirm_invalid_name_redirects_back(self):
        self.client.force_login(self.superuser)
        response = self.client.get(self.confirm_url, {'name': 'temp'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.wizard_url)
