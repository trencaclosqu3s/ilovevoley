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

    def test_club_with_notifications_disabled_excludes_its_recipients(self):
        """Si la organización desactiva los avisos, su staff no los recibe (#236)."""
        self.org_a.notify_match_changes = False
        self.org_a.save(update_fields=['notify_match_changes'])

        log = MatchChangeLog.objects.create(
            match=self.match,
            change_type='venue',
            field_name='venue',
            old_value='Pabellón A',
            new_value='Pabellón B',
            is_last_minute=True,
        )

        with override_settings(MATCH_CHANGE_NOTIFY_STAFF_ENABLED=True):
            sent_count = notify_match_changes([log])

        self.assertEqual(sent_count, 1)
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        recipients = email.to + email.bcc
        self.assertNotIn('delegat@santjosep.com', recipients)
        self.assertNotIn('coach@santjosep.com', recipients)
        self.assertIn('manager@manacor.com', recipients)

    def test_superuser_receives_global_copy_in_production(self):
        """El superusuario recibe copia de todos los tenants aunque no sea staff (#236)."""
        User.objects.create_superuser(username='root', email='root@isitech.es', password='x')

        log = MatchChangeLog.objects.create(
            match=self.match,
            change_type='venue',
            field_name='venue',
            old_value='Pabellón A',
            new_value='Pabellón B',
            is_last_minute=True,
        )

        with override_settings(MATCH_CHANGE_NOTIFY_STAFF_ENABLED=True):
            notify_match_changes([log])

        recipients = mail.outbox[0].to + mail.outbox[0].bcc
        self.assertIn('root@isitech.es', recipients)

    def test_team_without_club_still_notified(self):
        """Un equipo sin club vinculado no tiene configuración que lo silencie (#236)."""
        team_no_club = Team.objects.create(name='SELECCIÓN', federation_id='t-sel')
        person = Person.objects.create(
            first_name='Sele', last_name='Delegat',
            email='delegat@seleccion.com', organization=self.org_a,
        )
        StaffRole.objects.create(
            person=person, team=team_no_club, role='delegate',
            season=self.season, is_active=True,
        )
        match = Match.objects.create(
            league=self.league, home_team=team_no_club, away_team=self.team_b,
            match_date=timezone.now() + timedelta(days=2), venue='Pabellón S',
        )
        log = MatchChangeLog.objects.create(
            match=match, change_type='venue', field_name='venue',
            old_value='A', new_value='B', is_last_minute=True,
        )

        with override_settings(MATCH_CHANGE_NOTIFY_STAFF_ENABLED=True):
            notify_match_changes([log])

        recipients = mail.outbox[0].to + mail.outbox[0].bcc
        self.assertIn('delegat@seleccion.com', recipients)

    def test_superuser_flag_off_in_test_mode_sends_only_test_recipient(self):
        """MATCH_CHANGE_NOTIFY_SUPERUSERS=False también aplica en modo pruebas (#236)."""
        User.objects.create_superuser(username='root2', email='root2@isitech.es', password='x')
        log = MatchChangeLog.objects.create(
            match=self.match, change_type='venue', field_name='venue',
            old_value='A', new_value='B', is_last_minute=True,
        )

        with override_settings(
            MATCH_CHANGE_NOTIFY_STAFF_ENABLED=False,
            MATCH_CHANGE_NOTIFY_SUPERUSERS=False,
            MATCH_CHANGE_TEST_RECIPIENT='test_admin@isitech.es',
        ):
            notify_match_changes([log])

        self.assertEqual(
            mail.outbox[0].to + mail.outbox[0].bcc, ['test_admin@isitech.es']
        )

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

    def test_organizations_by_club_resolves_batch_in_single_query(self):
        """El mapeo club->organización del lote se resuelve con una sola consulta (#200)."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from ilovevoley.competitions.services.notifications import _organizations_by_club

        match2 = Match.objects.create(
            league=self.league, home_team=self.team_a, away_team=self.team_b,
            match_date=timezone.now(), venue='Pabellón B',
        )
        matches = list(
            Match.objects.select_related('home_team', 'away_team')
            .filter(id__in=[self.match.id, match2.id])
        )
        with CaptureQueriesContext(connection) as ctx:
            by_club = _organizations_by_club(matches)

        self.assertEqual(len(ctx.captured_queries), 1)
        self.assertEqual(by_club[self.club_a.id].slug, 'sant-josep')
        self.assertEqual(by_club[self.club_b.id].slug, 'manacor')
