"""Tests para los servicios de validación, aprobación y comparación de actas manuales.

Protege las reglas de negocio de revisión:
- Aprobación atómica que genera MatchLineup solo con datos válidos (dorsales 0-99 sin duplicar).
- Manejo no bloqueante de discrepancias en parciales frente a los oficiales federativos.
- Detección de partidos sancionados sin alterar los tanteos oficiales.
- Comparación por dorsal entre lo leído en el acta y la plantilla (PlayerRole).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from ilovevoley.competitions.models import League, Match, MatchActaPhoto, MatchLineup
from ilovevoley.competitions.services.acta_review import (
    approve_acta_photo,
    get_acta_roster_comparison,
    reject_acta_photo,
    validate_acta_data,
)
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.rosters.models import Person, PlayerRole
from ilovevoley.teams.models import Club, Team, TeamIdentity

User = get_user_model()


class ActaReviewValidationAndApprovalTests(TestCase):
    """
    Protege la validación de actas y los servicios de aprobación y rechazo.
    """

    def setUp(self):
        self.season = Season.objects.create(name='2025-26', is_current=True)
        self.category = Category.objects.create(name='Infantil')
        self.club = Club.objects.create(federation_id='100', official_name='CLUB SANT JOSEP')
        self.org, _ = Organization.objects.update_or_create(
            slug='santjosep',
            defaults={
                'name': 'Sant Josep',
                'club': self.club,
                'is_active': True,
                'club_team_names': {'Infantil': 'SANT JOSEP'},
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
            name='CV MANACOR',
            federation_id='t2',
            category=self.category,
            is_active=True,
        )
        self.league = League.objects.create(name='Liga Infantil', season=self.season, federation_id='8500')
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team,
            away_team=self.rival,
            federation_id='85271',
            round_number=1,
            match_date=timezone.now(),
            set_scores=[[25, 10], [25, 11], [25, 11]],
            home_score=3,
            away_score=0,
        )
        self.photo = MatchActaPhoto.objects.create(
            match=self.match,
            source_url='https://www.voleibolib.net/pdf.asp?o=85271.jpg',
            status='pending_review',
        )
        self.user = User.objects.create_user(username='coach', email='coach@santjosep.org', password='password123')

        # Jugadores en la plantilla
        self.p1 = Person.objects.create(first_name='Marc', last_name='Oliver', birth_year=2012)
        self.p2 = Person.objects.create(first_name='Pau', last_name='Raya', birth_year=2012)
        PlayerRole.objects.create(
            person=self.p1,
            identity=self.identity,
            season=self.season,
            jersey_number=4,
            is_active=True,
        )
        PlayerRole.objects.create(
            person=self.p2,
            identity=self.identity,
            season=self.season,
            jersey_number=7,
            is_active=True,
        )

        self.valid_data = {
            'home_team': 'SANT JOSEP',
            'away_team': 'CV MANACOR',
            'home_convocados': ['4 Oliver', '7 Raya'],
            'away_convocados': ['1 Gomez', '9 Perez'],
            'sets': [
                {'title': 'Set 1', 'home_points': 25, 'away_points': 10},
                {'title': 'Set 2', 'home_points': 25, 'away_points': 11},
                {'title': 'Set 3', 'home_points': 25, 'away_points': 11},
            ],
            'observations': '',
        }

    def test_approve_acta_photo_with_valid_data_creates_lineups_and_sets_approved(self):
        """Aprobación con datos válidos crea MatchLineup y marca estado approved con revisor."""
        ok, warnings = approve_acta_photo(self.photo, self.valid_data, user=self.user)
        self.assertTrue(ok)
        self.assertEqual(len(warnings), 0)

        self.photo.refresh_from_db()
        self.assertEqual(self.photo.status, 'approved')
        self.assertEqual(self.photo.reviewed_by, self.user)
        self.assertIsNotNone(self.photo.reviewed_at)

        # Verifica que se crearon los MatchLineup correspondientes
        lineups = MatchLineup.objects.filter(match=self.match)
        self.assertEqual(lineups.count(), 4)

        # Verifica que el jugador del tenant resolvió a su Person vía dorsal
        oliver_lineup = lineups.get(team=self.team, jersey_number=4)
        self.assertEqual(oliver_lineup.person, self.p1)
        self.assertEqual(oliver_lineup.name_acta, 'Oliver')
        self.assertTrue(oliver_lineup.is_convocado)

        # Verifica que el rival sin plantilla registrada tiene Person en None
        rival_lineup = lineups.get(team=self.rival, jersey_number=1)
        self.assertIsNone(rival_lineup.person)
        self.assertEqual(rival_lineup.name_acta, 'Gomez')

    def test_approve_acta_photo_with_duplicate_dorsal_fails_and_saves_errors(self):
        """Dorsal duplicado en el mismo equipo bloquea la aprobación y no crea ningún MatchLineup."""
        invalid_data = dict(self.valid_data)
        invalid_data['home_convocados'] = ['4 Oliver', '4 Raya']

        ok, errors = approve_acta_photo(self.photo, invalid_data, user=self.user)
        self.assertFalse(ok)
        self.assertTrue(any('duplicado' in e.lower() for e in errors))

        self.photo.refresh_from_db()
        self.assertNotEqual(self.photo.status, 'approved')
        self.assertTrue(len(self.photo.validation_errors) > 0)
        self.assertFalse(MatchLineup.objects.filter(match=self.match).exists())

    def test_approve_acta_photo_with_out_of_range_dorsal_fails(self):
        """Dorsal negativo o mayor a 99 bloquea la aprobación."""
        invalid_data = dict(self.valid_data)
        invalid_data['home_convocados'] = ['105 Oliver']

        ok, errors = approve_acta_photo(self.photo, invalid_data, user=self.user)
        self.assertFalse(ok)
        self.assertTrue(any('fuera del rango' in e.lower() for e in errors))

        self.photo.refresh_from_db()
        self.assertNotEqual(self.photo.status, 'approved')
        self.assertFalse(MatchLineup.objects.filter(match=self.match).exists())

    def test_validation_set_scores_mismatch_warns_without_blocking_approval(self):
        """Discrepancia en parciales leídos genera un aviso no bloqueante y conserva tanteo federativo."""
        data_different_scores = dict(self.valid_data)
        data_different_scores['sets'] = [
            {'title': 'Set 1', 'home_points': 25, 'away_points': 22},
            {'title': 'Set 2', 'home_points': 25, 'away_points': 20},
            {'title': 'Set 3', 'home_points': 25, 'away_points': 19},
        ]

        ok, warnings = approve_acta_photo(self.photo, data_different_scores, user=self.user)
        self.assertTrue(ok)
        self.assertTrue(any('no coinciden' in w.lower() for w in warnings))

        # El resultado oficial de la federación en Match.set_scores NO se sobreescribe
        self.match.refresh_from_db()
        self.assertEqual(self.match.set_scores, [[25, 10], [25, 11], [25, 11]])

    def test_validation_penalty_result_flags_warning_without_blocking(self):
        """Partidos con resultado sancionado (0-25x3 o penalty) emiten aviso para revisión humana."""
        self.match.set_scores = [[0, 25], [0, 25], [0, 25]]
        self.match.result_penalized = True
        self.match.save(update_fields=['set_scores', 'result_penalized'])

        data = dict(self.valid_data)
        data['sets'] = []

        is_valid, errors, warnings = validate_acta_data(self.match, data)
        self.assertTrue(is_valid)
        self.assertTrue(any('sancionado' in w.lower() for w in warnings))

    def test_reject_acta_photo_marks_status_rejected_with_reason(self):
        """Rechazo del acta actualiza estado a 'rejected' y guarda motivo en extraction_meta."""
        ok = reject_acta_photo(self.photo, user=self.user, reason='Foto completamente borrosa')
        self.assertTrue(ok)

        self.photo.refresh_from_db()
        self.assertEqual(self.photo.status, 'rejected')
        self.assertEqual(self.photo.reviewed_by, self.user)
        self.assertEqual(self.photo.extraction_meta.get('reject_reason'), 'Foto completamente borrosa')


class ActaRosterComparisonTests(TestCase):
    """
    Protege el servicio de comparación por dorsal entre lo leído y la plantilla (PlayerRole).
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
            federation_id='99999',
            round_number=1,
            match_date=timezone.now(),
        )

        # Plantilla tenant: dorsal 4 (Oliver), dorsal 7 (Raya), dorsal 12 (Gomez)
        self.p1 = Person.objects.create(first_name='Marc', last_name='Oliver', birth_year=2014)
        self.p2 = Person.objects.create(first_name='Pau', last_name='Raya', birth_year=2014)
        self.p3 = Person.objects.create(first_name='Lucas', last_name='Gomez', birth_year=2014)

        PlayerRole.objects.create(person=self.p1, identity=self.identity, season=self.season, jersey_number=4, is_active=True)
        PlayerRole.objects.create(person=self.p2, identity=self.identity, season=self.season, jersey_number=7, is_active=True)
        PlayerRole.objects.create(person=self.p3, identity=self.identity, season=self.season, jersey_number=12, is_active=True)

    def test_comparison_flags_matches_and_mismatches_and_missing_players(self):
        """La comparativa detecta coincidencias, apellidos discordantes (Lepe vs Raya) y ausentes en el acta."""
        data = {
            'home_convocados': [
                '4 Oliver',      # Coincide exactamente
                '7 Lepe',        # Dorsal 7 existe en plantilla pero apellido no casa (Raya vs Lepe)
            ],
            'away_convocados': ['10 RivalPlayer'],
        }

        comparison = get_acta_roster_comparison(self.match, data)

        home = comparison['home']
        self.assertTrue(home['is_tenant'])
        self.assertEqual(len(home['players']), 2)

        # Jugador 4 coincide
        p4 = home['players'][0]
        self.assertEqual(p4['jersey_number'], 4)
        self.assertEqual(p4['name_acta'], 'Oliver')
        self.assertEqual(p4['roster_name'], 'Oliver')
        self.assertTrue(p4['matches'])
        self.assertTrue(p4['is_in_roster'])

        # Jugador 7: está en plantilla pero el apellido no coincide (ej: error OCR Lepe por Raya)
        p7 = home['players'][1]
        self.assertEqual(p7['jersey_number'], 7)
        self.assertEqual(p7['name_acta'], 'Lepe')
        self.assertEqual(p7['roster_name'], 'Raya')
        self.assertFalse(p7['matches'])
        self.assertTrue(p7['is_in_roster'])

        # Jugador 12 está en plantilla pero no apareció en el acta
        missing = home['missing_from_acta']
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]['jersey_number'], 12)
        self.assertEqual(missing[0]['roster_name'], 'Gomez')
