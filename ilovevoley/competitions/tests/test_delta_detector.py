from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from ilovevoley.competitions.models import League, Match, MatchChangeLog
from ilovevoley.competitions.services.delta_detector import detect_and_record_match_changes
from ilovevoley.teams.models import Club, Team


class DeltaDetectorTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.club = Club.objects.create(federation_id='c-1', official_name='CV SANT JOSEP')
        cls.team_a = Team.objects.create(name='SANT JOSEP A', federation_id='t-1', club=cls.club)
        cls.team_b = Team.objects.create(name='CV ALGAIDA', federation_id='t-2')

        cls.league = League.objects.create(
            name='1a Balear', federation_id='l-1',
            visibility_type='main', is_our_team_related=True, is_active=True,
        )

    def test_detect_match_date_change_last_minute(self):
        # Partido programado para dentro de 3 días
        original_date = timezone.now() + timedelta(days=3)
        match = Match.objects.create(
            league=self.league,
            home_team=self.team_a,
            away_team=self.team_b,
            match_date=original_date,
            venue='Polideportivo Municipal',
            status='scheduled',
        )

        new_date = original_date + timedelta(hours=2)
        new_data = {
            'match_date': new_date,
            'venue': 'Polideportivo Municipal',
        }

        changes = detect_and_record_match_changes(match, new_data)
        self.assertEqual(len(changes), 1)
        log = changes[0]
        self.assertEqual(log.change_type, 'datetime')
        self.assertEqual(log.field_name, 'match_date')
        self.assertTrue(log.is_last_minute)
        expected_str = timezone.localtime(new_date).strftime('%d/%m/%Y %H:%M')
        self.assertIn(expected_str, log.new_value)


        # Verificar que se ha guardado en BD
        self.assertTrue(MatchChangeLog.objects.filter(id=log.id).exists())

    def test_detect_match_date_change_not_last_minute(self):
        # Partido programado para dentro de 20 días
        original_date = timezone.now() + timedelta(days=20)
        match = Match.objects.create(
            league=self.league,
            home_team=self.team_a,
            away_team=self.team_b,
            match_date=original_date,
            venue='Polideportivo Municipal',
            status='scheduled',
        )

        new_date = original_date + timedelta(days=1)
        new_data = {
            'match_date': new_date,
        }

        changes = detect_and_record_match_changes(match, new_data)
        self.assertEqual(len(changes), 1)
        log = changes[0]
        self.assertEqual(log.change_type, 'datetime')
        self.assertFalse(log.is_last_minute)

    def test_detect_venue_change(self):
        original_date = timezone.now() + timedelta(days=2)
        match = Match.objects.create(
            league=self.league,
            home_team=self.team_a,
            away_team=self.team_b,
            match_date=original_date,
            venue='Pabellón A',
            field_address='Calle Uno 1',
        )

        new_data = {
            'venue': 'Pabellón B',
            'field_address': 'Avenida Dos 2',
        }

        changes = detect_and_record_match_changes(match, new_data)
        self.assertEqual(len(changes), 2)
        types = {c.field_name for c in changes}
        self.assertEqual(types, {'venue', 'field_address'})
        self.assertTrue(all(c.change_type == 'venue' for c in changes))
        self.assertTrue(all(c.is_last_minute for c in changes))

    def test_detect_status_change_to_postponed(self):
        original_date = timezone.now() + timedelta(days=1)
        match = Match.objects.create(
            league=self.league,
            home_team=self.team_a,
            away_team=self.team_b,
            match_date=original_date,
            status='scheduled',
        )

        new_data = {
            'status': 'postponed',
        }

        changes = detect_and_record_match_changes(match, new_data)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].change_type, 'status')
        self.assertEqual(changes[0].old_value, 'scheduled')
        self.assertEqual(changes[0].new_value, 'postponed')

    def test_detect_score_discrepancy(self):
        original_date = timezone.now() - timedelta(days=1)
        match = Match.objects.create(
            league=self.league,
            home_team=self.team_a,
            away_team=self.team_b,
            match_date=original_date,
            status='finished',
            home_score=3,
            away_score=1,
        )

        new_data = {
            'home_score': 3,
            'away_score': 2,
        }

        changes = detect_and_record_match_changes(match, new_data)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].change_type, 'score')
        self.assertEqual(changes[0].field_name, 'away_score')
        self.assertEqual(changes[0].old_value, '1')
        self.assertEqual(changes[0].new_value, '2')

    def test_idempotence_no_changes_detected(self):
        original_date = timezone.now() + timedelta(days=4)
        match = Match.objects.create(
            league=self.league,
            home_team=self.team_a,
            away_team=self.team_b,
            match_date=original_date,
            venue='Pabellón Central',
            status='scheduled',
        )

        new_data = {
            'match_date': original_date,
            'venue': 'Pabellón Central',
            'status': 'scheduled',
        }

        changes = detect_and_record_match_changes(match, new_data)
        self.assertEqual(len(changes), 0)
        self.assertEqual(MatchChangeLog.objects.count(), 0)

    def test_lifecycle_scheduled_to_finished_not_recorded(self):
        """Finalizar un partido es ciclo de vida normal, no alteración federativa."""
        match = Match.objects.create(
            league=self.league,
            home_team=self.team_a,
            away_team=self.team_b,
            match_date=timezone.now() - timedelta(hours=3),
            status='scheduled',
        )

        changes = detect_and_record_match_changes(match, {'status': 'finished'})

        self.assertEqual(changes, [])
        self.assertEqual(MatchChangeLog.objects.filter(change_type='status').count(), 0)

    def test_lifecycle_in_progress_to_finished_not_recorded(self):
        match = Match.objects.create(
            league=self.league,
            home_team=self.team_a,
            away_team=self.team_b,
            match_date=timezone.now() - timedelta(hours=1),
            status='in_progress',
        )

        changes = detect_and_record_match_changes(match, {'status': 'finished'})

        self.assertEqual(changes, [])

    def test_non_lifecycle_status_change_still_recorded(self):
        """Una corrección federativa posterior (finished -> scheduled) sí se registra."""
        match = Match.objects.create(
            league=self.league,
            home_team=self.team_a,
            away_team=self.team_b,
            match_date=timezone.now() - timedelta(days=1),
            status='finished',
            home_score=3,
            away_score=1,
        )

        changes = detect_and_record_match_changes(match, {'status': 'scheduled'})

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].change_type, 'status')
        self.assertEqual(changes[0].new_value, 'scheduled')

    def test_withdrawn_to_scheduled_logged_but_not_notified(self):
        """El vaivén withdrawn/scheduled se audita pero no genera avisos por email (#235)."""
        match = Match.objects.create(
            league=self.league,
            home_team=self.team_a,
            away_team=self.team_b,
            match_date=timezone.now() + timedelta(days=2),
            status='withdrawn',
        )

        with patch(
            'ilovevoley.competitions.services.notifications.notify_match_changes'
        ) as mock_notify:
            changes = detect_and_record_match_changes(match, {'status': 'scheduled'})

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].change_type, 'status')
        self.assertEqual(changes[0].old_value, 'withdrawn')
        self.assertEqual(changes[0].new_value, 'scheduled')
        mock_notify.assert_not_called()

    def test_status_change_to_postponed_still_notified(self):
        """Un aplazamiento real sigue generando aviso."""
        match = Match.objects.create(
            league=self.league,
            home_team=self.team_a,
            away_team=self.team_b,
            match_date=timezone.now() + timedelta(days=2),
            status='scheduled',
        )

        with patch(
            'ilovevoley.competitions.services.notifications.notify_match_changes'
        ) as mock_notify:
            changes = detect_and_record_match_changes(match, {'status': 'postponed'})

        self.assertEqual(len(changes), 1)
        mock_notify.assert_called_once()
