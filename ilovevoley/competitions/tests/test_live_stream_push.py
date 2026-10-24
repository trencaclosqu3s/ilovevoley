import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
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


@override_settings(SCOREBOARD_STREAM_TOKEN='s3cret', ALLOWED_HOSTS=['santjust.ilovevoley.es'])
class ScoreboardStreamWebhookTest(TestCase):
    """Webhook del marcador que pone el directo en el partido en ventana (#575)."""

    URL = '/competitions/api/stream/live/'
    LIVE = 'https://www.youtube.com/@canal/live'

    def setUp(self):
        LiveStreamPushTest.setUp(self)
        self.match.stream_url = ''
        self.match.save(update_fields=['stream_url'])

    def _post(self, token='s3cret'):
        headers = {'HTTP_AUTHORIZATION': f'Bearer {token}'} if token else {}
        return self.client.post(
            self.URL, json.dumps({'url': self.LIVE}), content_type='application/json',
            HTTP_HOST='santjust.ilovevoley.es', **headers,
        )

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_rejects_missing_or_wrong_token(self, mock_push):
        """Sin token válido nadie puede publicar un directo ni disparar la push."""
        self.assertEqual(self._post(token=None).status_code, 403)
        self.assertEqual(self._post(token='otro').status_code, 403)

        self.match.refresh_from_db()
        self.assertEqual(self.match.stream_url, '')
        mock_push.assert_not_called()

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_single_match_saves_url_and_pushes_once(self, mock_push):
        """El marcador reintenta en cada corte de 4G: la push sale una sola vez."""
        with self.captureOnCommitCallbacks(execute=True):
            first = self._post()
            second = self._post()

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.match.refresh_from_db()
        self.assertEqual(self.match.stream_url, self.LIVE)
        mock_push.assert_called_once()

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_several_matches_in_window_conflict(self, mock_push):
        """Con dos partidos en ventana no se adivina: 409 y ninguno cambia."""
        other = Match.objects.create(
            league=self.league, home_team=self.team1, away_team=self.team2,
            match_date=timezone.now() - timedelta(hours=1), status='scheduled',
        )

        self.assertEqual(self._post().status_code, 409)

        self.assertFalse(Match.objects.filter(pk__in=[self.match.pk, other.pk]).exclude(stream_url='').exists())
        mock_push.assert_not_called()
