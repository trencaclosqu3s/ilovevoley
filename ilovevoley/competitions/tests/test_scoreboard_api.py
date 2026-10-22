import json
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
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

    def test_invalid_or_non_string_url_returns_400(self):
        """IN-01: un tipo de url no textual o vacío devuelve 400 'url required' en vez de 500."""
        for bad_url in [123, ['https://example.com'], {'url': 'x'}, True, '', '   ']:
            with self.subTest(bad_url=bad_url):
                response = self._post({'url': bad_url, 'match_id': self.match.pk})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {'success': False, 'error': 'url required'})


@override_settings(SCOREBOARD_STREAM_TOKEN='s3cret', ALLOWED_HOSTS=['santjust.ilovevoley.es'])
class ScoreboardMatchesTodayTest(TestCase):
    """GET de partidos de hoy del club para el marcador (BASE-04, D-04..D-08)."""

    URL = '/competitions/api/matches/today/'

    def setUp(self):
        from ilovevoley.competitions.tests.test_live_stream_push import LiveStreamPushTest

        LiveStreamPushTest.setUp(self)

    def _today_at(self, hour, minute=0):
        return timezone.localtime(timezone.now()).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )

    def _get(self, token='s3cret'):
        headers = {'HTTP_AUTHORIZATION': f'Bearer {token}'} if token else {}
        return self.client.get(
            self.URL, HTTP_HOST='santjust.ilovevoley.es', **headers,
        )

    @patch('django.utils.timezone.now')
    def test_today_list_only_own_club_open_matches_in_local_day(self, mock_now):
        """D-06 y D-04/D-05: solo partidos abiertos de hoy de este club, ordenados por hora."""
        tz = timezone.get_current_timezone()
        mock_now.return_value = timezone.make_aware(datetime(2026, 6, 15, 15, 0), tz)
        early = Match.objects.create(
            league=self.league, home_team=self.team1, away_team=self.team2,
            match_date=self._today_at(10), status='scheduled',
        )
        late = Match.objects.create(
            league=self.league, home_team=self.team1, away_team=self.team2,
            match_date=self._today_at(18), status='scheduled',
        )
        Match.objects.create(
            league=self.league, home_team=self.team1, away_team=self.team2,
            match_date=self._today_at(11), status='finished',
        )
        Match.objects.create(
            league=self.league, home_team=self.team1, away_team=self.team2,
            match_date=self._today_at(13), status='cancelled',
        )
        Match.objects.create(
            league=self.league, home_team=self.team1, away_team=self.team2,
            match_date=self._today_at(12) + timedelta(days=1), status='scheduled',
        )
        other_club = Club.objects.create(official_name='Otro Club', federation_id='OT02')
        Organization.objects.create(name='Otro CV Hoy', slug='otroclubhoy', club=other_club)
        other_team = Team.objects.create(
            name='Otro Hoy', club=other_club, federation_id='OT-T2', category=self.category,
        )
        Match.objects.create(
            league=self.league, home_team=other_team, away_team=self.team2,
            match_date=self._today_at(12), status='scheduled',
        )

        response = self._get()

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['date'], '2026-06-15')
        self.assertEqual([match['id'] for match in body['matches']], [early.pk, late.pk])
        self.assertEqual([match['time'] for match in body['matches']], ['10:00', '18:00'])

    @patch('django.utils.timezone.now')
    def test_today_list_colors_and_logo_fallbacks(self, mock_now):
        """D-07/D-08: colores de la Organization activa; escudo del club si el equipo no tiene."""
        tz = timezone.get_current_timezone()
        mock_now.return_value = timezone.make_aware(datetime(2026, 6, 15, 15, 0), tz)
        self.org.primary_color = '#112233'
        self.org.secondary_color = ''
        self.org.save(update_fields=['primary_color', 'secondary_color'])
        media_root = tempfile.mkdtemp()
        with override_settings(MEDIA_ROOT=media_root):
            self.club.logo.save(
                'club.png',
                SimpleUploadedFile('club.png', b'\x89PNG\r\n', content_type='image/png'),
                save=True,
            )
            Match.objects.create(
                league=self.league, home_team=self.team1, away_team=self.team2,
                match_date=self._today_at(12), status='scheduled',
            )
            response = self._get()

        self.assertEqual(response.status_code, 200)
        match = response.json()['matches'][0]
        home = match['home_team']
        away = match['away_team']
        self.assertEqual(home['name'], 'Senior A')
        self.assertEqual(home['primary_color'], '#112233')
        self.assertIsNone(home['secondary_color'])
        self.assertTrue(home['logo'].startswith('http://') or home['logo'].startswith('https://'))
        self.assertIn('santjust.ilovevoley.es', home['logo'])
        self.assertEqual(away['name'], 'Rival B')
        self.assertIsNone(away['logo'])
        self.assertIsNone(away['primary_color'])
        self.assertIsNone(away['secondary_color'])

    def test_today_list_requires_token(self):
        """BASE-03: el GET de partidos de hoy usa el mismo token; sin él no sale ningún partido."""
        Match.objects.create(
            league=self.league, home_team=self.team1, away_team=self.team2,
            match_date=timezone.now(), status='scheduled',
        )

        response = self._get(token=None)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {'success': False, 'error': 'forbidden'})
        self.assertNotIn('Senior A', response.content.decode())


@override_settings(SCOREBOARD_STREAM_TOKEN='s3cret', ALLOWED_HOSTS=['santjust.ilovevoley.es'])
class ScoreboardMatchResultTest(TestCase):
    """Reglas de negocio del endpoint de resultado del marcador (#576).

    Justificación (docs/ai-guidelines/testing-guidelines.md):
    - D-05: validación del marcador de sets y coherencia/ganador de cada parcial
      (con ``set_scores`` opcional para cuando se usan los botones ``set +/-``).
    - D-07: un resultado federativo previo (acta o penalización) bloquea con 409.
    - D-06: reenviar corrige el marcador pero envía la push una sola vez.
    No se duplican 403/405 del decorador ``scoreboard_api``.
    """

    URL = '/competitions/api/match/result/'

    def setUp(self):
        from ilovevoley.competitions.tests.test_live_stream_push import LiveStreamPushTest

        LiveStreamPushTest.setUp(self)

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
    def test_valid_result_saves_scores_set_scores_and_pushes_once(self, mock_push):
        """D-05/D-06: guarda sets, parciales (o [] si faltan) y finaliza con push única."""
        partials = [[25, 20], [22, 25], [25, 18], [25, 23]]
        with self.captureOnCommitCallbacks(execute=True):
            response = self._post({
                'match_id': self.match.pk,
                'home_score': 3,
                'away_score': 1,
                'set_scores': partials,
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {'success': True, 'match_id': self.match.pk, 'notified': True},
        )
        self.match.refresh_from_db()
        self.assertEqual(self.match.status, 'finished')
        self.assertEqual((self.match.home_score, self.match.away_score), (3, 1))
        self.assertEqual(self.match.set_scores, partials)
        mock_push.assert_called_once()

        # Sin set_scores (o []) también es válido y persiste [].
        no_partials = self._post({
            'match_id': self.match.pk,
            'home_score': 3,
            'away_score': 0,
        })
        self.assertEqual(no_partials.status_code, 200)
        self.match.refresh_from_db()
        self.assertEqual((self.match.home_score, self.match.away_score), (3, 0))
        self.assertEqual(self.match.set_scores, [])

    def test_inconsistent_or_tied_partials_return_400_without_changes(self):
        """D-05: parciales con más victorias de las declaradas, empatados o marcador inválido -> 400."""
        bad_payloads = [
            {
                'match_id': self.match.pk,
                'home_score': 3,
                'away_score': 1,
                'set_scores': [[20, 25], [22, 25], [25, 18], [25, 23]],
            },
            {
                'match_id': self.match.pk,
                'home_score': 3,
                'away_score': 0,
                'set_scores': [[20, 20], [25, 18], [25, 20]],
            },
            {
                'match_id': self.match.pk,
                'home_score': 2,
                'away_score': 1,
                'set_scores': [[25, 20], [20, 25], [25, 18]],
            },
        ]
        for payload in bad_payloads:
            with self.subTest(payload=payload):
                response = self._post(payload)
                self.assertEqual(response.status_code, 400)

        self.match.refresh_from_db()
        self.assertEqual(self.match.status, 'scheduled')
        self.assertIsNone(self.match.home_score)
        self.assertIsNone(self.match.away_score)
        self.assertIsNone(self.match.set_scores)

    def test_federation_result_returns_409_without_changes(self):
        """D-07: si ya hay acta o penalización federativa, devuelve 409 y no modifica el partido."""
        self.match.home_score = 0
        self.match.away_score = 3
        self.match.status = 'finished'
        self.match.acta_data = {'sets': []}
        self.match.save(update_fields=['home_score', 'away_score', 'status', 'acta_data'])

        response = self._post({
            'match_id': self.match.pk,
            'home_score': 3,
            'away_score': 1,
            'set_scores': [[25, 20], [22, 25], [25, 18], [25, 23]],
        })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {'success': False, 'error': 'federation result'})
        self.match.refresh_from_db()
        self.assertEqual((self.match.home_score, self.match.away_score), (0, 3))

        self.match.acta_data = None
        self.match.result_penalized = True
        self.match.save(update_fields=['acta_data', 'result_penalized'])

        penalized = self._post({
            'match_id': self.match.pk,
            'home_score': 3,
            'away_score': 0,
        })
        self.assertEqual(penalized.status_code, 409)
        self.match.refresh_from_db()
        self.assertEqual((self.match.home_score, self.match.away_score), (0, 3))

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_resending_valid_result_corrects_score_without_second_push(self, mock_push):
        """D-03/D-06: reenviar corrige el marcador y devuelve notified=false sin repetir push."""
        with self.captureOnCommitCallbacks(execute=True):
            first = self._post({
                'match_id': self.match.pk,
                'home_score': 3,
                'away_score': 1,
                'set_scores': [[25, 20], [22, 25], [25, 18], [25, 23]],
            })
            second_partials = [[25, 20], [22, 25], [25, 18], [21, 25], [15, 12]]
            second = self._post({
                'match_id': self.match.pk,
                'home_score': 3,
                'away_score': 2,
                'set_scores': second_partials,
            })

        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()['notified'])
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.json()['notified'])
        self.match.refresh_from_db()
        self.assertEqual((self.match.home_score, self.match.away_score), (3, 2))
        self.assertEqual(self.match.set_scores, second_partials)
        mock_push.assert_called_once()
