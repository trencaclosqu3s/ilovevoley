"""Tests del motor de redacción con LLM (#551).

Protegen lo que no se puede dejar al modelo: que el texto con cifras inventadas o sin
``{nombre}`` se descarte, que la clave del OCR nunca pague la narrativa (D5) y que los
cortes de la API se distingan de un texto mal escrito (D2, D6) para reintentar solo lo
recuperable. No se testea el prompt literal ni que el modelo escriba bien.
"""

import json
from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase, override_settings

from ilovevoley.core import narrative

FACTS = {'partidos_jugados': 14, 'victorias': 9, 'equipo': 'Cadete 2', 'temporada': '2025-26', 'genero': 'f'}
CALL = {'locale': 'es', 'max_chars': 200, 'style': 'wrapped'}
ENABLED = {'LLM_NARRATIVE_ENABLED': True, 'LLM_NARRATIVE_API_KEY': 'k', 'LLM_NARRATIVE_MIN_INTERVAL': 0}


def model_says(text):
    return patch.object(narrative, '_post_to_provider', return_value=json.dumps({'text': text}))


def http_response(status, body=None):
    response = MagicMock(status_code=status, text='boom')
    response.json.return_value = body
    return response


@override_settings(**ENABLED)
class ValidationTests(SimpleTestCase):
    def test_valid_text_is_normalized(self):
        with model_says('  {nombre}  ha jugado   14 partidos con el Cadete 2. '):
            text = narrative.redact(FACTS, **CALL)
        self.assertEqual(text, '{nombre} ha jugado 14 partidos con el Cadete 2.')

    def test_invalid_texts_are_discarded(self):
        cases = {
            'cifra inventada': '{nombre} ganó 15 partidos.',
            'cifra de la temporada, no un contador': '{nombre} jugó en 2025.',
            'sin marcador': 'Ha jugado 14 partidos.',
            'salto de línea': '{nombre} ha jugado\n14 partidos.',
            'demasiado largo': '{nombre} ' + 'x' * 200,
            'resto de plantilla': '{nombre} ha jugado {partidos_jugados} partidos.',
            'vacío': '   ',
        }
        for name, text in cases.items():
            with self.subTest(name), model_says(text):
                with self.assertRaises(narrative.NarrativeDiscarded):
                    narrative.redact(FACTS, **CALL)

    def test_season_can_be_mentioned_but_its_numbers_are_not_free_figures(self):
        with model_says('{nombre} ha jugado 14 partidos en la temporada 2025-26.'):
            self.assertIn('2025-26', narrative.redact(FACTS, **CALL))
        with model_says('{nombre} ha jugado 14 partidos desde 2025.'):
            with self.assertRaises(narrative.NarrativeDiscarded):
                narrative.redact(FACTS, **CALL)

    def test_numbers_compare_by_value_not_text(self):
        with model_says('{nombre} ha jugado 014 partidos.'):
            self.assertIn('014', narrative.redact(FACTS, **CALL))

    def test_fill_name_replaces_every_marker(self):
        self.assertEqual(narrative.fill_name('{nombre} y {nombre}', 'Marta'), 'Marta y Marta')


class DisabledTests(SimpleTestCase):
    @override_settings(LLM_NARRATIVE_ENABLED=True, LLM_NARRATIVE_API_KEY='', GEMINI_API_KEY='clave-ocr')
    def test_ocr_key_is_never_a_fallback(self):
        with patch.object(narrative.requests, 'post') as post:
            self.assertIsNone(narrative.redact(FACTS, **CALL))
        post.assert_not_called()

    @override_settings(LLM_NARRATIVE_ENABLED=False, LLM_NARRATIVE_API_KEY='k')
    def test_switch_off_makes_no_call(self):
        with patch.object(narrative.requests, 'post') as post:
            self.assertIsNone(narrative.redact(FACTS, **CALL))
        post.assert_not_called()


@override_settings(**ENABLED)
class ProviderErrorTests(SimpleTestCase):
    def redact_with(self, **post_kwargs):
        with patch.object(narrative.requests, 'post', **post_kwargs):
            return narrative.redact(FACTS, **CALL)

    def test_network_failures_and_overload_are_transient(self):
        for name, kwargs in {
            'timeout': {'side_effect': requests.exceptions.Timeout()},
            'red': {'side_effect': requests.exceptions.ConnectionError()},
            '429': {'return_value': http_response(429)},
            '503': {'return_value': http_response(503)},
        }.items():
            with self.subTest(name), self.assertRaises(narrative.NarrativeTransientError):
                self.redact_with(**kwargs)

    def test_other_http_errors_are_not_transient_nor_discarded(self):
        # Un 404 (modelo mal escrito) debe verse y no consumir el intento (D2).
        with self.assertRaises(narrative.NarrativeError) as ctx:
            self.redact_with(return_value=http_response(404))
        self.assertNotIsInstance(ctx.exception, (narrative.NarrativeTransientError, narrative.NarrativeDiscarded))

    def test_200_without_text_is_discarded_so_it_does_not_cut_the_batch_every_night(self):
        # Bloqueo por seguridad: sin `candidates`. Como NarrativeError, la misma fila pararía la tanda siempre.
        with self.assertRaises(narrative.NarrativeDiscarded):
            self.redact_with(return_value=http_response(200, {'promptFeedback': {'blockReason': 'SAFETY'}}))
        with self.assertRaises(narrative.NarrativeDiscarded):
            self.redact_with(return_value=http_response(200, {'candidates': [{'finishReason': 'SAFETY'}]}))

    def test_model_reply_that_is_not_json_text_is_discarded(self):
        body = {'candidates': [{'content': {'parts': [{'text': 'no es json'}]}}]}
        with self.assertRaises(narrative.NarrativeDiscarded):
            self.redact_with(return_value=http_response(200, body))


@override_settings(**{**ENABLED, 'LLM_NARRATIVE_MIN_INTERVAL': 4.5})
class ThrottleTests(SimpleTestCase):
    def test_second_call_waits_out_the_interval(self):
        # Sin la pausa, una tanda de 20 textos supera los 15/min y el resto de la noche da 429.
        ok = http_response(200, {'candidates': [{'content': {'parts': [{'text': '{"text": "x"}'}]}}]})
        with patch.object(narrative.requests, 'post', return_value=ok), \
                patch.object(narrative.time, 'sleep') as sleep, \
                patch.object(narrative.time, 'monotonic', side_effect=[100.0, 100.0, 101.0, 101.0]):
            narrative._last_call = 0.0
            narrative._post_to_provider('a')
            narrative._post_to_provider('b')
        sleep.assert_called_once_with(3.5)
