"""Tests para el servicio de lectura de actas manuales con Gemini Vision.

Protege el contrato de datos con Gemini (esquema compatible con parse_acta_lineup),
la inyección de contexto de plantillas conocidas del tenant para evitar alucinaciones,
el manejo de errores transitorios (429/503) para no perder actas y el interruptor
de configuración ACTA_VISION_ENABLED.
"""

import json
from unittest.mock import MagicMock, patch

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone

from ilovevoley.competitions.models import League, Match, MatchActaPhoto
from ilovevoley.competitions.services.acta_vision import (
    ActaVisionBrokenJsonError,
    ActaVisionError,
    ActaVisionTransientError,
    build_acta_context,
    build_acta_prompt,
    parse_acta_vision_result,
    process_acta_photo_batch,
    read_acta,
)
from ilovevoley.competitions.tasks import process_pending_acta_photos_task
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.rosters.models import Person, PlayerRole
from ilovevoley.teams.models import Club, Team, TeamIdentity


class ActaVisionServiceTests(TestCase):
    """
    Protege la integración REST con Gemini y la normalización al esquema de parse_acta_lineup.
    """

    def setUp(self):
        self.context = {
            'home_team': 'SANT JOSEP',
            'away_team': 'CV MANACOR',
            'tenant_roster': [(1, 'Oliver'), (7, 'Raya')],
            'tenant_team_name': 'SANT JOSEP',
        }
        self.sample_gemini_payload = {
            'rotation_degrees_needed': 0,
            'format': 'paper_alevin',
            'confidence': 'high',
            'home_team': 'SANT JOSEP',
            'away_team': 'CV MANACOR',
            'home_captain': 'Oliver',
            'away_captain': 'Perez',
            'home_coach': 'Entrenador 1',
            'away_coach': '',
            'home_convocados': ['1 Oliver', '7 Raya'],
            'away_convocados': ['4 Perez', '10 Gomez'],
            'sets': [
                {'title': 'Set 1', 'home_points': 25, 'away_points': 18},
                {'title': 'Set 2', 'home_points': 25, 'away_points': 20},
            ],
            'observations': 'Partido sin incidencias',
            'referees': ['Arbitro Principal'],
            'officials': [],
        }

    def _mock_gemini_response(self, text, status_code=200):
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.text = text
        mock_resp.json.return_value = {
            'candidates': [
                {
                    'content': {
                        'parts': [{'text': text}],
                    },
                }
            ],
            'usageMetadata': {'totalTokenCount': 1200},
        }
        return mock_resp

    @patch('requests.post')
    def test_read_acta_valid_json_returns_parse_acta_lineup_schema(self, mock_post):
        """Respuesta JSON válida de Gemini produce exactamente las claves de parse_acta_lineup."""
        text_response = json.dumps(self.sample_gemini_payload)
        mock_post.return_value = self._mock_gemini_response(text_response)

        result = read_acta(b'fake_jpeg_bytes', self.context, api_key='test-key')

        expected_keys = {
            'home_team',
            'away_team',
            'home_captain',
            'away_captain',
            'home_convocados',
            'away_convocados',
            'sets',
            'observations',
            'home_coach',
            'away_coach',
            'referees',
            'officials',
        }
        self.assertTrue(expected_keys.issubset(set(result.keys())))
        self.assertEqual(result['home_team'], 'SANT JOSEP')
        self.assertEqual(result['home_convocados'], ['1 Oliver', '7 Raya'])
        self.assertEqual(len(result['sets']), 2)
        # Metadatos preservados
        self.assertIn('_meta', result)
        self.assertEqual(result['_meta']['format'], 'paper_alevin')
        self.assertEqual(result['_meta']['usage']['totalTokenCount'], 1200)

    @patch('requests.post')
    def test_read_acta_broken_json_raises_broken_json_error(self, mock_post):
        """Texto truncado o malformado devuelto por el modelo eleva ActaVisionBrokenJsonError."""
        mock_post.return_value = self._mock_gemini_response('{"home_team": "SANT JOSEP", truncated...')

        with self.assertRaises(ActaVisionBrokenJsonError):
            read_acta(b'fake_jpeg_bytes', self.context, api_key='test-key')

    @patch('requests.post')
    def test_read_acta_503_raises_transient_error(self, mock_post):
        """Error 503 por alta demanda eleva ActaVisionTransientError para reintento posterior."""
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = 'The model is overloaded. Please try again later.'
        mock_post.return_value = mock_resp

        with self.assertRaises(ActaVisionTransientError):
            read_acta(b'fake_jpeg_bytes', self.context, api_key='test-key')

    @patch('requests.post')
    def test_read_acta_429_rate_limit_raises_transient_error(self, mock_post):
        """Error 429 por límite de cuota eleva ActaVisionTransientError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = 'Resource exhausted'
        mock_post.return_value = mock_resp

        with self.assertRaises(ActaVisionTransientError):
            read_acta(b'fake_jpeg_bytes', self.context, api_key='test-key')

    @patch('requests.post')
    def test_read_acta_error_payload_raises_appropriate_error(self, mock_post):
        """Payload con campo 'error' de la API de Google es interpretado correctamente."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'error': {'code': 503, 'message': 'Unavailable'},
        }
        mock_post.return_value = mock_resp

        with self.assertRaises(ActaVisionTransientError):
            read_acta(b'fake_jpeg_bytes', self.context, api_key='test-key')

    def test_read_acta_missing_api_key_raises_value_error(self):
        """Falta de clave de API lanza ValueError explícito."""
        with override_settings(GEMINI_API_KEY=''):
            with self.assertRaises(ValueError):
                read_acta(b'fake_jpeg_bytes', self.context, api_key='')

    def test_parse_acta_vision_result_normalizes_dict_convocados(self):
        """El normalizador convierte convocados estructurados como dict a cadenas '<dorsal> <apellido>'."""
        raw = {
            'home_convocados': [{'number': 12, 'name': 'Garcia'}, '15 Lopez'],
            'away_convocados': [{'dorsal': 4, 'apellido': 'Sanchez'}],
        }
        res = parse_acta_vision_result(raw, context=self.context)
        self.assertEqual(res['home_convocados'], ['12 Garcia', '15 Lopez'])
        self.assertEqual(res['away_convocados'], ['4 Sanchez'])


class ActaVisionContextTests(TestCase):
    """
    Protege la construcción de contexto del partido y prompt para el modelo:
    garantiza que la plantilla oficial del equipo tenant se incluye para evitar alucinaciones.
    """

    def setUp(self):
        self.season = Season.objects.create(name='2025-26', is_current=True)
        self.category = Category.objects.create(name='Alevin')
        self.club = Club.objects.create(federation_id='100', official_name='CLUB SANT JOSEP')
        self.org, _ = Organization.objects.update_or_create(
            slug='santjosep',
            defaults={
                'name': 'Sant Josep',
                'club': self.club,
                'is_active': True,
                'club_team_names': {'Alevin': 'SANT JOSEP'},
            },
        )
        self.identity = TeamIdentity.objects.create(
            club=self.club,
            category=self.category,
            core_name='SANT JOSEP',
            core_name_normalized='SANT JOSEP',
        )
        self.team = Team.objects.create(
            name='SANT JOSEP',
            federation_id='t1',
            club=self.club,
            category=self.category,
            identity=self.identity,
            is_active=True,
        )
        self.rival = Team.objects.create(
            name='RIVAL',
            federation_id='t2',
            category=self.category,
            is_active=True,
        )
        self.league = League.objects.create(name='Liga Alevin', season=self.season, federation_id='9000')
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team,
            away_team=self.rival,
            federation_id='88888',
            round_number=1,
            match_date=timezone.now(),
        )

        # Jugadores en la plantilla del tenant
        p1 = Person.objects.create(first_name='Marc', last_name='Oliver', birth_year=2014)
        p2 = Person.objects.create(first_name='Pau', last_name='Raya', birth_year=2014)
        PlayerRole.objects.create(
            person=p1,
            identity=self.identity,
            season=self.season,
            jersey_number=5,
            is_active=True,
        )
        PlayerRole.objects.create(
            person=p2,
            identity=self.identity,
            season=self.season,
            jersey_number=11,
            is_active=True,
        )

    def test_build_acta_context_includes_tenant_roster(self):
        """El contexto del partido incluye los dorsales y apellidos de la plantilla tenant."""
        context = build_acta_context(self.match)
        self.assertTrue(context['is_home_tenant'])
        self.assertEqual(context['tenant_team_name'], 'SANT JOSEP')
        self.assertEqual(context['tenant_roster'], [(5, 'Oliver'), (11, 'Raya')])

    def test_build_acta_prompt_instructs_model_not_to_invent(self):
        """El prompt incluye la plantilla conocida e instruye no inventar jugadores."""
        context = build_acta_context(self.match)
        prompt = build_acta_prompt(context)
        self.assertIn('5 Oliver', prompt)
        self.assertIn('11 Raya', prompt)
        self.assertIn('NO inventes', prompt)


class ActaVisionBatchExecutionTests(TestCase):
    """
    Protege el flujo por lotes y la tarea Celery:
    verifica transiciones de estado, idempotencia ante fallos transitorios y control por ACTA_VISION_ENABLED.
    """

    def setUp(self):
        self.season = Season.objects.create(name='2025-26', is_current=True)
        self.category = Category.objects.create(name='Alevin')
        self.club = Club.objects.create(federation_id='100', official_name='CLUB SANT JOSEP')
        self.org, _ = Organization.objects.update_or_create(
            slug='santjosep',
            defaults={
                'name': 'Sant Josep',
                'club': self.club,
                'is_active': True,
                'club_team_names': {'Alevin': 'SANT JOSEP'},
            },
        )
        self.team = Team.objects.create(
            name='SANT JOSEP',
            federation_id='t1',
            club=self.club,
            category=self.category,
            is_active=True,
        )
        self.rival = Team.objects.create(
            name='RIVAL',
            federation_id='t2',
            category=self.category,
            is_active=True,
        )
        self.league = League.objects.create(name='Liga Alevin', season=self.season, federation_id='9000')
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team,
            away_team=self.rival,
            federation_id='77777',
            round_number=1,
            match_date=timezone.now(),
        )
        self.photo = MatchActaPhoto.objects.create(
            match=self.match,
            source_url='https://www.voleibolib.net/pdf.asp?o=77777.jpg',
            status='downloaded',
        )
        self.photo.image.save('acta_77777.jpg', ContentFile(b'fake_jpeg_content'), save=True)

    @override_settings(ACTA_VISION_ENABLED=False)
    def test_batch_skips_vision_when_disabled(self):
        """Con ACTA_VISION_ENABLED=False no se llama al modelo y la foto pasa a pending_review sin datos,
        para poder teclear los convocados a mano en el admin sin quedar atascada ni ocupar el lote."""
        with patch('ilovevoley.competitions.services.acta_vision.read_acta') as mock_read:
            processed = process_acta_photo_batch(limit=5)
            self.assertEqual(processed, 1)
            mock_read.assert_not_called()

        self.photo.refresh_from_db()
        self.assertEqual(self.photo.status, 'pending_review')
        self.assertIsNone(self.photo.extracted_data)

    @override_settings(ACTA_VISION_ENABLED=True, GEMINI_API_KEY='valid-key')
    @patch('ilovevoley.competitions.services.acta_vision.read_acta')
    def test_batch_success_transitions_photo_to_pending_review(self, mock_read):
        """Lectura exitosa guarda extracted_data y transiciona el estado a 'pending_review'."""
        mock_read.return_value = {
            'home_team': 'SANT JOSEP',
            'away_team': 'RIVAL',
            'home_convocados': ['1 Oliver'],
            'away_convocados': ['3 Gomez'],
            'sets': [{'title': 'Set 1', 'home_points': 25, 'away_points': 20}],
            '_meta': {'format': 'paper_alevin', 'confidence': 'high'},
        }

        processed = process_acta_photo_batch(limit=5)
        self.assertEqual(processed, 1)

        self.photo.refresh_from_db()
        self.assertEqual(self.photo.status, 'pending_review')
        self.assertIsNotNone(self.photo.extracted_data)
        self.assertEqual(self.photo.extracted_data['home_team'], 'SANT JOSEP')
        self.assertEqual(self.photo.extraction_meta['format'], 'paper_alevin')

    @override_settings(ACTA_VISION_ENABLED=True, GEMINI_API_KEY='valid-key')
    @patch('ilovevoley.competitions.services.acta_vision.read_acta')
    def test_batch_503_leaves_photo_pending_read(self, mock_read):
        """Error 503 deja la foto en pending_read sin perderla para la siguiente ejecución."""
        mock_read.side_effect = ActaVisionTransientError('503 Service Unavailable')

        processed = process_acta_photo_batch(limit=5)
        self.assertEqual(processed, 0)

        self.photo.refresh_from_db()
        self.assertEqual(self.photo.status, 'pending_read')
        self.assertIsNone(self.photo.extracted_data)

    @override_settings(ACTA_VISION_ENABLED=True, GEMINI_API_KEY='valid-key')
    @patch('ilovevoley.competitions.services.acta_vision.read_acta')
    def test_celery_task_delegates_to_batch_processor(self, mock_read):
        """La tarea Celery explícita ejecuta el procesador por lotes."""
        mock_read.return_value = {
            'home_team': 'SANT JOSEP',
            'away_team': 'RIVAL',
            'home_convocados': [],
            'away_convocados': [],
            'sets': [],
            '_meta': {'format': 'paper_alevin'},
        }

        result = process_pending_acta_photos_task(limit=2)
        self.assertEqual(result, 1)
