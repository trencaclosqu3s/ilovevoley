from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from ilovevoley.competitions.models import League, Match
from ilovevoley.competitions.services.notifications import notify_match_live_stream
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.teams.models import Club, Team
from ilovevoley.users.models import NotificationType

User = get_user_model()


class LiveStreamPushTest(TestCase):
    """Pruebas del servicio de notificación push de retransmisión en directo (#359)."""

    def setUp(self):
        self.club = Club.objects.create(official_name='Sant Just', federation_id='SJ01')
        self.org = Organization.objects.create(
            name='CV Sant Just', slug='santjust', club=self.club
        )
        self.season = Season.objects.create(name='2025-26', start_year=2025, is_current=True)
        self.category = Category.objects.create(name='Senior Femenino')
        self.team1 = Team.objects.create(
            name='Senior A', club=self.club, federation_id='T01', category=self.category
        )
        self.team2 = Team.objects.create(name='Rival B', federation_id='T02')
        self.league = League.objects.create(name='1a Balear', season=self.season)
        self.league.categories.add(self.category)

        # Partido dentro de la ventana de directo (en 15 minutos)
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team1,
            away_team=self.team2,
            match_date=timezone.now() + timedelta(minutes=15),
            status='scheduled',
            stream_url='https://www.youtube.com/watch?v=live123',
        )

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_live_stream_push_sent_when_in_window(self, mock_push):
        """Un partido con stream_url en ventana de juego envía push de live_stream y marca stream_notified_at."""
        with self.captureOnCommitCallbacks(execute=True):
            sent = notify_match_live_stream(self.match)

        self.assertTrue(sent)
        mock_push.assert_called_once()
        _, kwargs = mock_push.call_args
        self.assertEqual(kwargs['organization_id'], self.org.id)
        self.assertEqual(kwargs['notification_type'], NotificationType.LIVE_STREAM)
        self.assertIn('En directo: Senior A vs Rival B', kwargs['title'])
        self.assertIn(self.category.id, kwargs['category_ids'])
        self.assertIn(f"/competitions/partidos/{self.match.id}/", kwargs['url'])

        self.match.refresh_from_db()
        self.assertIsNotNone(self.match.stream_notified_at)

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_live_stream_push_idempotent(self, mock_push):
        """Si ya se notificó el directo, sucesivas llamadas no reenvían el push."""
        with self.captureOnCommitCallbacks(execute=True):
            first = notify_match_live_stream(self.match)

        self.assertTrue(first)
        self.assertEqual(mock_push.call_count, 1)

        with self.captureOnCommitCallbacks(execute=True):
            second = notify_match_live_stream(self.match)

        self.assertFalse(second)
        self.assertEqual(mock_push.call_count, 1)

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_live_stream_push_not_sent_outside_window(self, mock_push):
        """Partidos fuera de la ventana (-30 min a +3 h) no envían push."""
        self.match.match_date = timezone.now() + timedelta(hours=4)
        self.match.save()

        with self.captureOnCommitCallbacks(execute=True):
            sent = notify_match_live_stream(self.match)

        self.assertFalse(sent)
        mock_push.assert_not_called()
        self.match.refresh_from_db()
        self.assertIsNone(self.match.stream_notified_at)

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_live_stream_push_not_sent_without_stream_url(self, mock_push):
        """Partidos sin stream_url no envían push."""
        self.match.stream_url = ''
        self.match.save()

        with self.captureOnCommitCallbacks(execute=True):
            sent = notify_match_live_stream(self.match)

        self.assertFalse(sent)
        mock_push.assert_not_called()
