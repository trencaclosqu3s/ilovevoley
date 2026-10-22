import json
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from ilovevoley.competitions.models import Match
from ilovevoley.core.models import Organization
from ilovevoley.teams.models import Club, Team


@override_settings(SCOREBOARD_STREAM_TOKEN='s3cret', ALLOWED_HOSTS=['santjust.ilovevoley.es'])
class ScoreboardApiMatchIdTest(TestCase):
    """match_id opcional del webhook del marcador (BASE-01, D-01, D-02)."""

    URL = '/competitions/api/stream/live/'
    LIVE = 'https://www.youtube.com/@canal/live'

    def setUp(self):
        # Import perezoso: si la clase queda en el módulo, pytest vuelve a
        # recolectar sus tests aquí.
        from ilovevoley.competitions.tests.test_live_stream_push import LiveStreamPushTest

        LiveStreamPushTest.setUp(self)
        self.match.stream_url = ''
        self.match.save(update_fields=['stream_url'])

    def _post(self, payload, token='s3cret'):
        headers = {'HTTP_AUTHORIZATION': f'Bearer {token}'} if token else {}
        return self.client.post(
            self.URL,
            json.dumps(payload),
            content_type='application/json',
            HTTP_HOST='santjust.ilovevoley.es',
            **headers,
        )

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_match_id_picks_that_match_among_several_in_window(self, mock_push):
        """BASE-01: con varios partidos en ventana, el id explícito elige cuál se actualiza."""
        other = Match.objects.create(
            league=self.league,
            home_team=self.team1,
            away_team=self.team2,
            match_date=timezone.now() - timedelta(hours=1),
            status='scheduled',
        )

        with self.captureOnCommitCallbacks(execute=True):
            response = self._post({'url': self.LIVE, 'match_id': other.pk})

        self.assertEqual(response.status_code, 200)
        other.refresh_from_db()
        self.match.refresh_from_db()
        self.assertEqual(other.stream_url, self.LIVE)
        self.assertEqual(self.match.stream_url, '')
        mock_push.assert_called_once()

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_unknown_or_foreign_match_id_is_404_without_window_fallback(self, mock_push):
        """D-01/D-04: un id inexistente o de otro club es 404 y no cae al partido propio en ventana."""
        other_club = Club.objects.create(official_name='Otro Club', federation_id='OT01')
        Organization.objects.create(name='Otro CV', slug='otroclub', club=other_club)
        other_team = Team.objects.create(
            name='Otro A', club=other_club, federation_id='OT-T1', category=self.category,
        )
        foreign = Match.objects.create(
            league=self.league,
            home_team=other_team,
            away_team=self.team2,
            match_date=timezone.now(),
            status='scheduled',
        )

        with self.captureOnCommitCallbacks(execute=True):
            missing = self._post({'url': self.LIVE, 'match_id': 999999})
            foreign_response = self._post({'url': self.LIVE, 'match_id': foreign.pk})

        self.assertEqual(missing.status_code, 404)
        self.assertEqual(foreign_response.status_code, 404)
        self.match.refresh_from_db()
        foreign.refresh_from_db()
        self.assertEqual(self.match.stream_url, '')
        self.assertEqual(foreign.stream_url, '')
        mock_push.assert_not_called()

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_explicit_match_outside_window_saves_url_without_push(self, mock_push):
        """D-02: un partido finalizado se guarda con match_id, pero no dispara la push."""
        self.match.status = 'finished'
        self.match.save(update_fields=['status'])

        response = self._post({'url': self.LIVE, 'match_id': self.match.pk})

        self.assertEqual(response.status_code, 200)
        self.match.refresh_from_db()
        self.assertEqual(self.match.stream_url, self.LIVE)
        self.assertIsNone(self.match.stream_notified_at)
        mock_push.assert_not_called()
