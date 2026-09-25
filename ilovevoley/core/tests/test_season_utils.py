from django.test import RequestFactory, TestCase

from ilovevoley.core.models import Season
from ilovevoley.core.season_utils import resolve_season_filter


class ResolveSeasonFilterTests(TestCase):
    """Contrato de `?season=`: sin parámetro -> activa; vacío -> todas; id -> esa."""

    def setUp(self):
        self.factory = RequestFactory()
        self.current = Season.objects.create(
            name='2026-27', start_year=2026, end_year=2027, is_current=True
        )
        self.past = Season.objects.create(name='2025-26', start_year=2025, end_year=2026)

    def _resolve(self, query=''):
        return resolve_season_filter(self.factory.get('/' + query))

    def test_sin_parametro_usa_la_activa(self):
        season, selected = self._resolve()
        self.assertEqual(season, self.current)
        self.assertEqual(selected, str(self.current.pk))

    def test_parametro_vacio_devuelve_todas(self):
        season, selected = self._resolve('?season=')
        self.assertIsNone(season)
        self.assertEqual(selected, '')

    def test_id_valido_devuelve_esa_temporada(self):
        season, selected = self._resolve(f'?season={self.past.pk}')
        self.assertEqual(season, self.past)
        self.assertEqual(selected, str(self.past.pk))

    def test_id_inexistente_cae_a_la_activa(self):
        season, _ = self._resolve('?season=999999')
        self.assertEqual(season, self.current)

    def test_id_no_numerico_cae_a_la_activa(self):
        season, selected = self._resolve('?season=abc')
        self.assertEqual(season, self.current)
        self.assertEqual(selected, str(self.current.pk))

    def test_nombre_de_temporada_cae_a_la_activa(self):
        season, _ = self._resolve('?season=2025-26')
        self.assertEqual(season, self.current)
