from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from ilovevoley.competitions.models import League, Match, MatchChangeLog
from ilovevoley.competitions.services.notifications import notify_match_changes
from ilovevoley.core.models import Organization, Season
from ilovevoley.rosters.models import Person, StaffRole
from ilovevoley.teams.models import Club, Team
from ilovevoley.users.models import Membership

User = get_user_model()


class MatchChangeNotificationsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.season = Season.objects.create(name='2026-27', start_year=2026, end_year=2027, is_current=True)
        cls.club_a = Club.objects.create(federation_id='c-a', official_name='CV SANT JOSEP')
        cls.club_b = Club.objects.create(federation_id='c-b', official_name='CV MANACOR')

        cls.org_a = Organization.objects.create(slug='sant-josep', name='Sant Josep Org', club=cls.club_a)
        cls.org_b = Organization.objects.create(slug='manacor', name='Manacor Org', club=cls.club_b)

        cls.team_a = Team.objects.create(name='SANT JOSEP A', federation_id='t-a', club=cls.club_a)
        cls.team_b = Team.objects.create(name='MANACOR B', federation_id='t-b', club=cls.club_b)

        cls.league = League.objects.create(
            name='1a Balear', federation_id='l-balear', season=cls.season,
            visibility_type='main', is_our_team_related=True, is_active=True,
        )

        cls.match = Match.objects.create(
            league=cls.league,
            home_team=cls.team_a,
            away_team=cls.team_b,
            match_date=timezone.now() + timedelta(days=2),
            venue='Pabellón A',
        )

        # Delegado para Team A
        cls.person_delegate = Person.objects.create(
            first_name='Pep', last_name='Delegat', email='delegat@santjosep.com', organization=cls.org_a
        )
        cls.staff_delegate = StaffRole.objects.create(
            person=cls.person_delegate, team=cls.team_a, role='delegate', season=cls.season, is_active=True
        )

        # Entrenador para Team A (vinculado a User con email)
        cls.user_coach = User.objects.create_user(username='coach_user', email='coach@santjosep.com')
        cls.person_coach = Person.objects.create(
            first_name='Toni', last_name='Coach', user=cls.user_coach, organization=cls.org_a
        )
        cls.staff_coach = StaffRole.objects.create(
            person=cls.person_coach, team=cls.team_a, role='head_coach', season=cls.season, is_active=True
        )

        # Manager de Org B (para probar fallback ya que Team B no tiene staff)
        cls.user_manager_b = User.objects.create_user(username='manager_b', email='manager@manacor.com')
        cls.membership_b = Membership.objects.create(
            user=cls.user_manager_b, organization=cls.org_b, role='manager', is_approved=True
        )

    def test_safe_mode_sends_only_to_test_recipient(self):
        log = MatchChangeLog.objects.create(
            match=self.match,
            change_type='datetime',
            field_name='match_date',
            old_value='29/09/2026 10:00',
            new_value='29/09/2026 12:00',
            is_last_minute=True,
        )

        with override_settings(
            MATCH_CHANGE_NOTIFY_STAFF_ENABLED=False,
            MATCH_CHANGE_TEST_RECIPIENT='test_admin@isitech.es',
        ):
            sent_count = notify_match_changes([log])

        self.assertEqual(sent_count, 1)
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ['test_admin@isitech.es'])
        self.assertIn('Modificación federativa', email.subject)
        self.assertIn('29/09/2026 12:00', email.body)

        log.refresh_from_db()
        self.assertTrue(log.notified)
        self.assertIsNotNone(log.notified_at)

    def test_production_mode_sends_to_staff_and_club_managers_fallback(self):
        log = MatchChangeLog.objects.create(
            match=self.match,
            change_type='venue',
            field_name='venue',
            old_value='Pabellón A',
            new_value='Pabellón B',
            is_last_minute=True,
        )

        with override_settings(
            MATCH_CHANGE_NOTIFY_STAFF_ENABLED=True,
        ):
            sent_count = notify_match_changes([log])

        self.assertEqual(sent_count, 1)
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        # Con múltiples destinatarios, van en BCC para proteger privacidad
        self.assertIn('delegat@santjosep.com', email.bcc)
        self.assertIn('coach@santjosep.com', email.bcc)
        self.assertIn('manager@manacor.com', email.bcc)


        log.refresh_from_db()
        self.assertTrue(log.notified)
        self.assertIsNotNone(log.notified_at)

    def test_already_notified_logs_are_skipped(self):
        log = MatchChangeLog.objects.create(
            match=self.match,
            change_type='datetime',
            field_name='match_date',
            old_value='29/09/2026 10:00',
            new_value='29/09/2026 12:00',
            is_last_minute=True,
            notified=True,
            notified_at=timezone.now(),
        )

        with override_settings(MATCH_CHANGE_TEST_RECIPIENT='test_admin@isitech.es'):
            sent_count = notify_match_changes([log])

        self.assertEqual(sent_count, 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_match_url_uses_home_club_subdomain(self):
        """El enlace del email apunta al subdominio del club local, no al dominio raíz."""
        log = MatchChangeLog.objects.create(
            match=self.match,
            change_type='venue',
            field_name='venue',
            old_value='Pabellón A',
            new_value='Pabellón B',
            is_last_minute=True,
        )

        with override_settings(
            MATCH_CHANGE_NOTIFY_STAFF_ENABLED=False,
            MATCH_CHANGE_TEST_RECIPIENT='test_admin@isitech.es',
            TENANT_BASE_DOMAIN='ilovevoley.test',
        ):
            notify_match_changes([log])

        body = mail.outbox[0].body
        self.assertIn('sant-josep.ilovevoley.test', body)
        self.assertIn(f'/competitions/partidos/{self.match.id}/', body)
