"""Pruebas del servicio get_team_season_summary.

Justificación según docs/ai-guidelines/testing-guidelines.md:
- Protege la regla de negocio de agregación de estadísticas de equipo por identidad y temporada.
- Protege la regla de negocio de selección de 'position' (torneo con más partidos jugados y desempate por updated_at).
- Verifica la derivación no trivial de set_difference y point_difference.
- Protege el aislamiento multi-tenant y los límites de temporada.
- Verifica el contrato estricto de salida (nunca exponer 'played' y devolver None si no hay registros).
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from ilovevoley.competitions.models import League, Standing
from ilovevoley.competitions.services.team_season_stats import get_team_season_summary
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.teams.models import Club, Team
from ilovevoley.teams.tests.helpers import identity_of


class TeamSeasonStatsServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.season = Season.objects.resolve('2026-2027')
        cls.other_season = Season.objects.resolve('2025-2026')
        cls.category = Category.objects.create(name='Senior Masculino', is_active=True)

        cls.club = Club.objects.create(federation_id='club-sj', official_name='CV Sant Josep')
        cls.other_club = Club.objects.create(federation_id='club-other', official_name='CV Altres')

        cls.tenant = Organization.objects.create(
            slug='sant-josep',
            name='Sant Josep',
            club=cls.club,
            club_team_names={'Senior': 'Sant Josep'},
            is_active=True,
        )
        cls.other_tenant = Organization.objects.create(
            slug='altres',
            name='Altres',
            club=cls.other_club,
            club_team_names={'Senior': 'Altres'},
            is_active=True,
        )

        cls.team = Team.objects.create(
            name='Sant Josep Senior',
            federation_id='team-sj-1',
            club=cls.club,
            category=cls.category,
        )
        cls.identity = identity_of(cls.team)

        cls.league_1 = League.objects.create(
            name='1a Balear - Liga Regular',
            federation_id='league-balear-1',
            season=cls.season,
            visibility_type='main',
            is_active=True,
            is_our_team_related=True,
        )
        cls.league_2 = League.objects.create(
            name='1a Balear - Playoff',
            federation_id='league-balear-playoff',
            season=cls.season,
            visibility_type='main',
            is_active=True,
            is_our_team_related=True,
        )
        cls.league_past = League.objects.create(
            name='1a Balear 2025-26',
            federation_id='league-balear-past',
            season=cls.other_season,
            visibility_type='main',
            is_active=True,
            is_our_team_related=True,
        )
        cls.league_other_tenant = League.objects.create(
            name='Superliga Altres',
            federation_id='league-altres',
            season=cls.season,
            visibility_type='main',
            is_active=True,
            is_our_team_related=True,
        )

    def test_returns_none_when_no_standings_exist(self):
        """Protege la regla de negocio: si no existen clasificaciones para el equipo en la temporada, retorna None."""
        summary = get_team_season_summary(self.identity, self.season, self.tenant)
        self.assertIsNone(summary)

        # Entradas nulas deben retornar None sin error
        self.assertIsNone(get_team_season_summary(None, self.season, self.tenant))
        self.assertIsNone(get_team_season_summary(self.identity, None, self.tenant))
        self.assertIsNone(get_team_season_summary(self.identity, self.season, None))

    def test_returns_none_for_different_season_or_other_tenant(self):
        """Protege el aislamiento multi-tenant y de temporadas: registros de otra temporada u otro club no filtran."""
        # Clasificación en temporada anterior
        Standing.objects.create(
            league=self.league_past,
            team=self.team,
            position=1,
            played=14,
            won=14,
            lost=0,
            sets_for=42,
            sets_against=5,
            points_for=1150,
            points_against=800,
            total_points=42,
        )
        # La temporada actual sigue sin clasificaciones
        self.assertIsNone(get_team_season_summary(self.identity, self.season, self.tenant))

        # Clasificación en la liga de otro tenant
        other_team = Team.objects.create(
            name='Altres Senior',
            federation_id='team-altres-1',
            club=self.other_club,
            category=self.category,
        )
        other_identity = identity_of(other_team)
        Standing.objects.create(
            league=self.league_other_tenant,
            team=other_team,
            position=2,
            played=10,
            won=8,
            lost=2,
            sets_for=25,
            sets_against=10,
            points_for=800,
            points_against=650,
            total_points=24,
        )
        # Nuestro tenant no debe ver la clasificación del otro equipo
        self.assertIsNone(get_team_season_summary(other_identity, self.season, self.tenant))

    def test_single_standing_passthrough_and_contract(self):
        """Verifica el paso directo de una única clasificación y que nunca se expone 'played'."""
        Standing.objects.create(
            league=self.league_1,
            team=self.team,
            position=2,
            played=12,
            won=9,
            lost=3,
            sets_for=30,
            sets_against=15,
            points_for=1050,
            points_against=900,
            total_points=27,
        )

        summary = get_team_season_summary(self.identity, self.season, self.tenant)

        expected = {
            'position': 2,
            'won': 9,
            'lost': 3,
            'sets_for': 30,
            'sets_against': 15,
            'set_difference': 15,
            'points_for': 1050,
            'points_against': 900,
            'point_difference': 150,
            'total_points': 27,
        }
        self.assertEqual(summary, expected)
        self.assertNotIn('played', summary)
        self.assertEqual(
            set(summary.keys()),
            {
                'position',
                'won',
                'lost',
                'sets_for',
                'sets_against',
                'set_difference',
                'points_for',
                'points_against',
                'point_difference',
                'total_points',
            },
        )

    def test_multi_standing_sums_metrics_and_picks_position_from_highest_played(self):
        """Protege la agregación de métricas y la elección de posición del torneo con más partidos jugados."""
        Standing.objects.create(
            league=self.league_1,
            team=self.team,
            position=3,
            played=14,
            won=10,
            lost=4,
            sets_for=34,
            sets_against=18,
            points_for=1200,
            points_against=1050,
            total_points=30,
        )
        Standing.objects.create(
            league=self.league_2,
            team=self.team,
            position=1,
            played=6,
            won=5,
            lost=1,
            sets_for=16,
            sets_against=6,
            points_for=520,
            points_against=430,
            total_points=15,
        )

        summary = get_team_season_summary(self.identity, self.season, self.tenant)

        self.assertIsNotNone(summary)
        # Posición tomada de league_1 (played=14 > played=6)
        self.assertEqual(summary['position'], 3)
        # Totales agregados
        self.assertEqual(summary['won'], 15)
        self.assertEqual(summary['lost'], 5)
        self.assertEqual(summary['sets_for'], 50)
        self.assertEqual(summary['sets_against'], 24)
        self.assertEqual(summary['set_difference'], 26)
        self.assertEqual(summary['points_for'], 1720)
        self.assertEqual(summary['points_against'], 1480)
        self.assertEqual(summary['point_difference'], 240)
        self.assertEqual(summary['total_points'], 45)
        self.assertNotIn('played', summary)

    def test_multi_standing_position_tie_breaker_newest_updated_at(self):
        """Protege el desempate de posición por updated_at más reciente cuando los partidos jugados coinciden."""
        now = timezone.now()
        s1 = Standing.objects.create(
            league=self.league_1,
            team=self.team,
            position=2,
            played=10,
            won=7,
            lost=3,
            sets_for=24,
            sets_against=12,
            points_for=820,
            points_against=700,
            total_points=21,
        )
        s2 = Standing.objects.create(
            league=self.league_2,
            team=self.team,
            position=4,
            played=10,
            won=6,
            lost=4,
            sets_for=20,
            sets_against=15,
            points_for=780,
            points_against=720,
            total_points=18,
        )

        Standing.objects.filter(pk=s1.pk).update(updated_at=now - timedelta(days=2))
        Standing.objects.filter(pk=s2.pk).update(updated_at=now)

        summary = get_team_season_summary(self.identity, self.season, self.tenant)
        self.assertEqual(summary['position'], 4)

        # Ahora invertimos: s1 más reciente que s2
        Standing.objects.filter(pk=s1.pk).update(updated_at=now + timedelta(days=1))
        summary_rev = get_team_season_summary(self.identity, self.season, self.tenant)
        self.assertEqual(summary_rev['position'], 2)

    def test_multi_team_same_identity_aggregates_across_teams(self):
        """Protege la consolidación de identidad cuando varios registros Team comparten identidad."""
        team_phase2 = Team.objects.create(
            name='Sant Josep Fase 2',
            federation_id='team-sj-phase2',
            club=self.club,
            category=self.category,
            identity=self.identity,
        )
        Standing.objects.create(
            league=self.league_1,
            team=self.team,
            position=2,
            played=10,
            won=8,
            lost=2,
            sets_for=26,
            sets_against=10,
            points_for=850,
            points_against=700,
            total_points=24,
        )
        Standing.objects.create(
            league=self.league_2,
            team=team_phase2,
            position=1,
            played=5,
            won=5,
            lost=0,
            sets_for=15,
            sets_against=2,
            points_for=420,
            points_against=310,
            total_points=15,
        )

        summary = get_team_season_summary(self.identity, self.season, self.tenant)

        self.assertIsNotNone(summary)
        self.assertEqual(summary['position'], 2)  # played=10 > played=5
        self.assertEqual(summary['won'], 13)
        self.assertEqual(summary['lost'], 2)
        self.assertEqual(summary['sets_for'], 41)
        self.assertEqual(summary['sets_against'], 12)
        self.assertEqual(summary['set_difference'], 29)
        self.assertEqual(summary['points_for'], 1270)
        self.assertEqual(summary['points_against'], 1010)
        self.assertEqual(summary['point_difference'], 260)
        self.assertEqual(summary['total_points'], 39)

    def test_accepts_team_instance_as_identity_arg(self):
        """Verifica la ergonomía de admitir una instancia de Team además de TeamIdentity."""
        Standing.objects.create(
            league=self.league_1,
            team=self.team,
            position=1,
            played=8,
            won=7,
            lost=1,
            sets_for=22,
            sets_against=6,
            points_for=680,
            points_against=510,
            total_points=21,
        )

        summary_with_team = get_team_season_summary(self.team, self.season, self.tenant)
        self.assertIsNotNone(summary_with_team)
        self.assertEqual(summary_with_team['position'], 1)

        # Equipo sin identidad configurada retorna None
        orphan_team = Team.objects.create(
            name='Huérfano',
            federation_id='team-orphan',
            club=self.club,
            category=self.category,
            identity=None,
        )
        self.assertIsNone(get_team_season_summary(orphan_team, self.season, self.tenant))
