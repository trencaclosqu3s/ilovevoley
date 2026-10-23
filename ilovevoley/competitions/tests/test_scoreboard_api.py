import json
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from ilovevoley.competitions.models import Match
from ilovevoley.competitions.scoreboard_api import (
    LIVE_STATE_TTL,
    live_resolve_cooldown_key,
    live_state_key,
)
from ilovevoley.competitions.services.youtube_live import resolve_live_watch_url
from ilovevoley.content.models import Video
from ilovevoley.core.models import Organization
from ilovevoley.core.security import UnsafeURL
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
        patcher = patch(
            'ilovevoley.competitions.scoreboard_api.resolve_live_watch_url',
            return_value=None,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

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


@override_settings(SCOREBOARD_STREAM_TOKEN='s3cret', ALLOWED_HOSTS=['santjust.ilovevoley.es'])
class ScoreboardStreamEndedTest(TestCase):
    """Resolución de watch?v= al inicio y creación de Video al fin (#577).

    Justificación (docs/ai-guidelines/testing-guidelines.md):
    - D-13: resolver @canal/live a watch?v= al inicio; si falla conserva @canal/live
      sin bloquear la notificación push.
    - D-14/D-18: al fin sin URL resoluble o con URL ajena no crea Video; sin match_id devuelve 400.
    - D-15/D-16: dedupe por (match, youtube_url) y sufijo «parte N» para grabaciones partidas.
    - D-17: sin SCOREBOARD_VIDEO_USER_ID válido devuelve 503 y no crea nada.
    """

    LIVE_URL = '/competitions/api/stream/live/'
    ENDED_URL = '/competitions/api/stream/ended/'
    CHANNEL_LIVE = 'https://www.youtube.com/@canal/live'
    WATCH_1 = 'https://www.youtube.com/watch?v=abcdefghijk'
    WATCH_2 = 'https://www.youtube.com/watch?v=12345678901'

    def setUp(self):
        from ilovevoley.competitions.tests.test_live_stream_push import LiveStreamPushTest

        LiveStreamPushTest.setUp(self)
        self.user = get_user_model().objects.create_user(
            username='scoreboard_video_bot',
            email='scoreboard@example.com',
            password='secret',
        )

    def _post(self, url, payload, token='s3cret'):
        headers = {'HTTP_AUTHORIZATION': f'Bearer {token}'} if token else {}
        return self.client.post(
            url,
            json.dumps(payload),
            content_type='application/json',
            HTTP_HOST='santjust.ilovevoley.es',
            **headers,
        )

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    @patch('ilovevoley.competitions.scoreboard_api.resolve_live_watch_url')
    def test_stream_live_resolves_watch_url_or_falls_back_to_channel_live(
        self, mock_resolve, mock_push
    ):
        """D-13: guarda watch?v= cuando resuelve; si devuelve None conserva @canal/live y envía push."""
        self.match.stream_url = ''
        self.match.save(update_fields=['stream_url'])
        mock_resolve.return_value = self.WATCH_1

        with self.captureOnCommitCallbacks(execute=True):
            res = self._post(self.LIVE_URL, {'url': self.CHANNEL_LIVE, 'match_id': self.match.pk})

        self.assertEqual(res.status_code, 200)
        self.match.refresh_from_db()
        self.assertEqual(self.match.stream_url, self.WATCH_1)
        mock_push.assert_called_once()

        # Si el resolver devuelve None, guarda @canal/live y sigue notificando.
        self.match.stream_url = ''
        self.match.stream_notified_at = None
        self.match.save(update_fields=['stream_url', 'stream_notified_at'])
        mock_resolve.return_value = None

        with self.captureOnCommitCallbacks(execute=True):
            fallback = self._post(
                self.LIVE_URL, {'url': self.CHANNEL_LIVE, 'match_id': self.match.pk}
            )

        self.assertEqual(fallback.status_code, 200)
        self.match.refresh_from_db()
        self.assertEqual(self.match.stream_url, self.CHANNEL_LIVE)
        self.assertEqual(mock_push.call_count, 2)

    def test_stream_ended_creates_video_dedupes_same_url_and_numbers_second_part(self):
        """D-15/D-16: crea Video con metadatos del partido, no duplica misma URL y numera parte 2."""
        self.match.stream_url = self.WATCH_1
        self.match.save(update_fields=['stream_url'])

        with self.settings(SCOREBOARD_VIDEO_USER_ID=self.user.pk):
            first = self._post(self.ENDED_URL, {'match_id': self.match.pk})
            repeat = self._post(self.ENDED_URL, {'match_id': self.match.pk})

            self.match.stream_url = self.WATCH_2
            self.match.save(update_fields=['stream_url'])
            second_part = self._post(self.ENDED_URL, {'match_id': self.match.pk})

        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()['created'])
        self.assertEqual(repeat.status_code, 200)
        self.assertFalse(repeat.json()['created'])
        self.assertEqual(first.json()['video_id'], repeat.json()['video_id'])

        self.assertEqual(second_part.status_code, 200)
        self.assertTrue(second_part.json()['created'])

        videos = list(Video.objects.filter(match=self.match).order_by('pk'))
        self.assertEqual(len(videos), 2)
        self.assertEqual(videos[0].title, 'Senior A - Rival B')
        self.assertEqual(videos[0].youtube_url, self.WATCH_1)
        self.assertEqual(videos[0].organization, self.org)
        self.assertEqual(videos[0].season, self.season)
        self.assertEqual(videos[0].category, self.category)
        self.assertEqual(videos[0].created_by, self.user)
        self.assertEqual(videos[1].title, 'Senior A - Rival B parte 2')
        self.assertEqual(videos[1].youtube_url, self.WATCH_2)

    @patch('ilovevoley.competitions.scoreboard_api.resolve_live_watch_url', return_value=None)
    def test_stream_ended_skips_unresolved_or_unsupported_url_and_requires_match_id(
        self, _mock_resolve
    ):
        """D-14/D-18: @canal/live sin resolver y URL no watch?v= no crean Video; sin match_id da 400."""
        with self.settings(SCOREBOARD_VIDEO_USER_ID=self.user.pk):
            self.match.stream_url = self.CHANNEL_LIVE
            self.match.save(update_fields=['stream_url'])
            unresolved = self._post(self.ENDED_URL, {'match_id': self.match.pk})

            self.match.stream_url = 'https://youtu.be/abcdefghijk'
            self.match.save(update_fields=['stream_url'])
            unsupported = self._post(self.ENDED_URL, {'match_id': self.match.pk})

            missing_id = self._post(self.ENDED_URL, {})

        self.assertEqual(unresolved.status_code, 200)
        self.assertEqual(
            unresolved.json(),
            {
                'success': True,
                'match_id': self.match.pk,
                'created': False,
                'reason': 'unresolved',
            },
        )
        self.assertEqual(unsupported.status_code, 200)
        self.assertEqual(
            unsupported.json(),
            {
                'success': True,
                'match_id': self.match.pk,
                'created': False,
                'reason': 'unsupported url',
            },
        )
        self.assertEqual(missing_id.status_code, 400)
        self.assertEqual(Video.objects.filter(match=self.match).count(), 0)

    def test_stream_ended_without_configured_user_returns_503(self):
        """D-17: sin SCOREBOARD_VIDEO_USER_ID válido responde 503 y no crea Video."""
        self.match.stream_url = self.WATCH_1
        self.match.save(update_fields=['stream_url'])

        with self.settings(SCOREBOARD_VIDEO_USER_ID=0), self.assertLogs(
            'ilovevoley.competitions.scoreboard_api', level='ERROR'
        ) as logs:
            response = self._post(self.ENDED_URL, {'match_id': self.match.pk})

        self.assertIn('SCOREBOARD_VIDEO_USER_ID', logs.output[0])
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(), {'success': False, 'error': 'video user not configured'}
        )
        self.assertEqual(Video.objects.filter(match=self.match).count(), 0)


class YoutubeLiveResolveTest(SimpleTestCase):
    """Parseo de canonical y barrera SSRF en resolve_live_watch_url (#577, D-13).

    Justificación (docs/ai-guidelines/testing-guidelines.md):
    Verifica una transformación de datos no trivial (extracción del id de 11
    caracteres desde <link rel="canonical">) y que hosts/esquemas ajenos o
    errores de safe_get se rechacen sin propagar excepciones.
    """

    @patch('ilovevoley.competitions.services.youtube_live.safe_get')
    def test_extracts_watch_url_from_canonical_and_normalizes_host(self, mock_get):
        mock_get.return_value = (
            b'<html><head>'
            b'<link rel="canonical" href="https://www.youtube.com/watch?v=dQw4w9WgXcQ">'
            b'</head></html>'
        )
        result = resolve_live_watch_url('https://youtube.com/@clubvoley/live')
        self.assertEqual(result, 'https://www.youtube.com/watch?v=dQw4w9WgXcQ')
        mock_get.assert_called_once()
        self.assertEqual(
            mock_get.call_args.args[0], 'https://www.youtube.com/@clubvoley/live'
        )
        # Sin la cookie de consentimiento, YouTube redirige a consent.youtube.com desde la UE.
        self.assertEqual(mock_get.call_args.kwargs['headers']['Cookie'], 'SOCS=CAI')

    @patch('ilovevoley.competitions.services.youtube_live.safe_get')
    def test_returns_none_when_canonical_is_not_watch_or_safe_get_fails(self, mock_get):
        mock_get.return_value = (
            b'<html><head>'
            b'<link rel="canonical" href="https://www.youtube.com/channel/UC123456">'
            b'</head></html>'
        )
        self.assertIsNone(
            resolve_live_watch_url('https://www.youtube.com/@clubvoley/live')
        )

        mock_get.side_effect = UnsafeURL('redirect blocked')
        self.assertIsNone(
            resolve_live_watch_url('https://www.youtube.com/@clubvoley/live')
        )

    @patch('ilovevoley.competitions.services.youtube_live.safe_get')
    def test_rejects_foreign_host_or_http_without_network(self, mock_get):
        for bad in [
            'https://evil.com/@clubvoley/live',
            'http://www.youtube.com/@clubvoley/live',
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            '',
            None,
        ]:
            self.assertIsNone(resolve_live_watch_url(bad))
        mock_get.assert_not_called()


@override_settings(
    SCOREBOARD_STREAM_TOKEN='s3cret',
    ALLOWED_HOSTS=['santjust.ilovevoley.es', 'otroclub.ilovevoley.es'],
)
class ScoreboardLiveStateTest(TestCase):
    """Recepción y lectura del estado en vivo del marcador (#578).

    Justificación (docs/ai-guidelines/testing-guidelines.md):
    - D-06: validación de cotas y tipos (rechaza bool como int, >99, parciales
      empatados, serve fuera de catálogo, visible no booleano) y filtrado estricto
      de claves antes de guardar en caché.
    - D-07: bloqueo con 409 fuera de ``is_live_window`` (partido cerrado o fuera de hora).
    - D-09/D-11/D-14/LIVE-03: lectura pública sin login desde otro subdominio que
      expone el subconjunto solo cuando hay clave, está en ventana y ``visible=True``.
    - D-05: escritura en caché con TTL explícito de 90 s (``LIVE_STATE_TTL``).
    """

    POST_URL = '/competitions/api/match/live-state/'

    def setUp(self):
        from ilovevoley.competitions.tests.test_live_stream_push import LiveStreamPushTest

        LiveStreamPushTest.setUp(self)
        cache.clear()
        other_club = Club.objects.create(official_name='Otro Club Live', federation_id='OT99')
        Organization.objects.create(name='Otro CV Live', slug='otroclub', club=other_club)

    def _valid_payload(self, **overrides):
        base = {
            'match_id': self.match.pk,
            'home_points': 18,
            'away_points': 15,
            'home_sets': 1,
            'away_sets': 0,
            'sets_history': [[25, 20]],
            'serve': 'home',
            'visible': True,
        }
        base.update(overrides)
        return base

    def _post(self, payload, token='s3cret'):
        headers = {'HTTP_AUTHORIZATION': f'Bearer {token}'} if token else {}
        return self.client.post(
            self.POST_URL,
            json.dumps(payload),
            content_type='application/json',
            HTTP_HOST='santjust.ilovevoley.es',
            **headers,
        )

    def _get_public(self, match_id=None, host='otroclub.ilovevoley.es'):
        pk = self.match.pk if match_id is None else match_id
        return self.client.get(
            f'/competitions/match/{pk}/live-state/',
            HTTP_HOST=host,
        )

    def test_invalid_payloads_return_400_and_valid_stores_only_subset(self):
        """D-06: rechaza fuera de cota/tipos con 400 sin escribir; válido guarda solo las 7 claves."""
        invalid_cases = [
            {'home_points': 100},
            {'away_points': True},
            {'sets_history': [[25, 25]]},
            {'serve': 'x'},
            {'visible': 'yes'},
        ]
        for overrides in invalid_cases:
            with self.subTest(overrides=overrides):
                res = self._post(self._valid_payload(**overrides))
                self.assertEqual(res.status_code, 400)
                self.assertIsNone(cache.get(live_state_key(self.match.pk)))

        res = self._post(
            self._valid_payload(
                home_name='Inyección',
                undo=[{'x': 1}],
                color='#ff0000',
            )
        )
        self.assertEqual(res.status_code, 200)
        cached = cache.get(live_state_key(self.match.pk))
        self.assertEqual(
            cached,
            {
                'home_points': 18,
                'away_points': 15,
                'home_sets': 1,
                'away_sets': 0,
                'sets_history': [[25, 20]],
                'serve': 'home',
                'visible': True,
            },
        )

    def test_finished_or_outside_window_match_returns_409_without_caching(self):
        """D-07: partido cerrado o fuera de is_live_window responde 409 y no escribe en caché."""
        self.match.status = 'finished'
        self.match.save(update_fields=['status'])

        res = self._post(self._valid_payload())
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json(), {'success': False, 'error': 'not live'})
        self.assertIsNone(cache.get(live_state_key(self.match.pk)))

    def test_public_get_across_tenants_respects_cache_visibility_and_window(self):
        """D-09/D-11/D-14/LIVE-03: GET sin login desde otro club según clave, visible y ventana."""
        empty_res = self._get_public()
        self.assertEqual(empty_res.status_code, 200)
        self.assertEqual(empty_res.json(), {'success': True, 'live': False})
        self.assertEqual(empty_res['Cache-Control'], 'no-store')

        self._post(self._valid_payload())
        live_res = self._get_public()
        self.assertEqual(live_res.status_code, 200)
        self.assertEqual(
            live_res.json(),
            {
                'success': True,
                'live': True,
                'home_points': 18,
                'away_points': 15,
                'home_sets': 1,
                'away_sets': 0,
                'sets_history': [[25, 20]],
                'serve': 'home',
                'visible': True,
            },
        )
        self.assertEqual(live_res['Cache-Control'], 'no-store')

        self._post(self._valid_payload(visible=False))
        hidden_res = self._get_public()
        self.assertEqual(hidden_res.status_code, 200)
        self.assertEqual(hidden_res.json(), {'success': True, 'live': False})

        self._post(self._valid_payload(visible=True))
        self.match.status = 'finished'
        self.match.save(update_fields=['status'])
        closed_res = self._get_public()
        self.assertEqual(closed_res.status_code, 200)
        self.assertEqual(closed_res.json(), {'success': True, 'live': False})

    def test_post_writes_cache_with_live_state_ttl(self):
        """D-05: cache.set recibe LIVE_STATE_TTL (90 s) como timeout."""
        with patch('ilovevoley.competitions.scoreboard_api.cache.set') as mock_set:
            res = self._post(self._valid_payload())

        self.assertEqual(res.status_code, 200)
        self.assertEqual(LIVE_STATE_TTL, 90)
        mock_set.assert_any_call(
            live_state_key(self.match.pk),
            {
                'home_points': 18,
                'away_points': 15,
                'home_sets': 1,
                'away_sets': 0,
                'sets_history': [[25, 20]],
                'serve': 'home',
                'visible': True,
            },
            LIVE_STATE_TTL,
        )

    @patch('ilovevoley.competitions.scoreboard_api.resolve_live_watch_url')
    def test_heartbeat_resolves_channel_live_once(self, mock_resolve):
        """D-02: un @canal/live se resuelve en el latido y el siguiente no vuelve a llamar.

        Protege la regla de guardar watch?v= durante el directo. El segundo latido
        ya no es @canal/live, así que no se vuelve a pedir a YouTube.
        """
        channel = 'https://www.youtube.com/@clubvoley/live'
        watch = 'https://www.youtube.com/watch?v=abc123DEF45'
        self.match.stream_url = channel
        self.match.save(update_fields=['stream_url'])
        mock_resolve.return_value = watch

        first = self._post(self._valid_payload())
        second = self._post(self._valid_payload())

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.match.refresh_from_db()
        self.assertEqual(self.match.stream_url, watch)
        self.assertEqual(mock_resolve.call_count, 1)

    @patch('ilovevoley.competitions.scoreboard_api.resolve_live_watch_url', return_value=None)
    def test_heartbeat_resolve_cooldown_until_key_deleted(self, mock_resolve):
        """D-02: si la resolución falla, no se reintenta hasta que caduque el cooldown.

        El latido llega cada 30 s. Sin el cooldown se martillearía YouTube en cada uno.
        """
        self.match.stream_url = 'https://www.youtube.com/@clubvoley/live'
        self.match.save(update_fields=['stream_url'])

        first = self._post(self._valid_payload())
        second = self._post(self._valid_payload())
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(mock_resolve.call_count, 1)

        cache.delete(live_resolve_cooldown_key(self.match.pk))
        third = self._post(self._valid_payload())
        self.assertEqual(third.status_code, 200)
        self.assertEqual(mock_resolve.call_count, 2)

    @patch(
        'ilovevoley.competitions.scoreboard_api.resolve_live_watch_url',
        side_effect=RuntimeError('youtube down'),
    )
    def test_heartbeat_resolve_exception_keeps_cached_state(self, _mock_resolve):
        """Una excepción al resolver no rompe el latido: 200 y el estado sigue en caché.

        Camino crítico del aviso en vivo: el marcador no puede recibir un 500
        porque YouTube o la caché fallen después de guardar el estado.
        """
        self.match.stream_url = 'https://www.youtube.com/@clubvoley/live'
        self.match.save(update_fields=['stream_url'])

        res = self._post(self._valid_payload())
        self.assertEqual(res.status_code, 200)
        self.assertIsNotNone(cache.get(live_state_key(self.match.pk)))
