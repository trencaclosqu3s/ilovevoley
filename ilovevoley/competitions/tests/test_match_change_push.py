from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from ilovevoley.competitions.models import League, Match
from ilovevoley.competitions.services.delta_detector import detect_and_record_match_changes
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.teams.models import Club, Team

User = get_user_model()


class MatchChangePushTest(TestCase):
    def setUp(self):
        self.club = Club.objects.create(official_name='Sant Just', federation_id='SJ01')
        self.org = Organization.objects.create(
            name='CV Sant Just', slug='santjust', club=self.club, notify_match_changes=True
        )
        self.user = User.objects.create_superuser(username='admin', email='a@test.es', password='pwd')
        self.season = Season.objects.create(name='2025-26', start_year=2025, is_current=True)
        self.category = Category.objects.create(name='Senior Femenino')
        self.team1 = Team.objects.create(
            name='Senior A', club=self.club, federation_id='T01', category=self.category
        )
        self.team2 = Team.objects.create(name='Rival B', federation_id='T02')
        self.league = League.objects.create(name='1a Balear', season=self.season)
        self.league.categories.add(self.category)
        self.match_date = timezone.now() + timedelta(days=3)
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team1,
            away_team=self.team2,
            match_date=self.match_date,
            venue='Pabellón Antiguo',
            status='scheduled',
        )

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_flag_disabled_by_default_sends_no_push(self, mock_push):
        """Con el flag desactivado (por defecto), los cambios federativos no envían push."""
        new_date = self.match_date + timedelta(hours=2)
        with self.captureOnCommitCallbacks(execute=True):
            detect_and_record_match_changes(self.match, {'match_date': new_date})

        mock_push.assert_not_called()

    @override_settings(MATCH_CHANGE_PUSH_ENABLED=True)
    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_flag_enabled_sends_push_per_change_type(self, mock_push):
        """Con flag activo, cada tipo de cambio envía push match_change con su título y cuerpo."""
        new_date = self.match_date + timedelta(hours=2)
        cases = {
            'datetime': ({'match_date': new_date}, 'Cambio de horario: Senior A vs Rival B', None),
            'venue': ({'venue': 'Polideportivo San Juan'}, 'Cambio de pista: Senior A vs Rival B', 'Polideportivo San Juan'),
            'postponed': ({'status': 'postponed'}, 'Partido aplazado: Senior A vs Rival B', 'aplazado'),
        }
        for label, (changes, expected_title, expected_body) in cases.items():
            with self.subTest(label):
                mock_push.reset_mock()
                with self.captureOnCommitCallbacks(execute=True):
                    detect_and_record_match_changes(self.match, changes)

                mock_push.assert_called_once()
                _, kwargs = mock_push.call_args
                self.assertEqual(kwargs['organization_id'], self.org.id)
                self.assertEqual(kwargs['notification_type'], 'match_change')
                self.assertIn(self.category.id, kwargs['category_ids'])
                self.assertIn(f"/competitions/partidos/{self.match.id}/", kwargs['url'])
                self.assertIn(expected_title, kwargs['title'])
                if expected_body is not None:
                    if label == 'postponed':
                        self.assertIn(expected_body, kwargs['body'].lower())
                    else:
                        self.assertIn(expected_body, kwargs['body'])

    @override_settings(MATCH_CHANGE_PUSH_ENABLED=True)
    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_multiple_changes_in_single_scrape_sends_single_grouped_push(self, mock_push):
        """Un partido con varios cambios (fecha y pista) en el mismo scrape genera un único aviso."""
        new_date = self.match_date + timedelta(days=1)
        with self.captureOnCommitCallbacks(execute=True):
            detect_and_record_match_changes(
                self.match,
                {'match_date': new_date, 'venue': 'Pabellón Polideportivo Central'}
            )

        self.assertEqual(mock_push.call_count, 1)
        _, kwargs = mock_push.call_args
        self.assertEqual(kwargs['organization_id'], self.org.id)
        self.assertIn('Cambio de horario y pista: Senior A vs Rival B', kwargs['title'])
        self.assertIn('Pabellón Polideportivo Central', kwargs['body'])

    @override_settings(MATCH_CHANGE_PUSH_ENABLED=True)
    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_org_with_notify_match_changes_false_does_not_receive_push(self, mock_push):
        """Si la organización tiene notify_match_changes=False, no recibe push."""
        self.org.notify_match_changes = False
        self.org.save(update_fields=['notify_match_changes'])

        new_date = self.match_date + timedelta(hours=2)
        with self.captureOnCommitCallbacks(execute=True):
            detect_and_record_match_changes(self.match, {'match_date': new_date})

        mock_push.assert_not_called()

    @override_settings(MATCH_CHANGE_PUSH_ENABLED=True)
    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_push_distinguishes_added_time_and_venue_from_changes(self, mock_push):
        """Cuando se confirma hora (desde 00:00) o pista (desde vacío), el push lo indica como confirmación."""
        target_day = timezone.localtime(timezone.now() + timedelta(days=3))
        placeholder_dt = target_day.replace(hour=0, minute=0, second=0, microsecond=0)
        confirmed_dt = target_day.replace(hour=17, minute=0, second=0, microsecond=0)

        match = Match.objects.create(
            league=self.league,
            home_team=self.team1,
            away_team=self.team2,
            match_date=placeholder_dt,
            venue='',
            status='scheduled',
        )

        with self.captureOnCommitCallbacks(execute=True):
            detect_and_record_match_changes(
                match, {'match_date': confirmed_dt, 'venue': 'Polideportivo Municipal'}
            )

        mock_push.assert_called_once()
        _, kwargs = mock_push.call_args
        self.assertIn('Horario y pista confirmados: Senior A vs Rival B', kwargs['title'])
        self.assertIn('Hora confirmada:', kwargs['body'])
        self.assertIn('Pista confirmada: Polideportivo Municipal', kwargs['body'])
