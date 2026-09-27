from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from ilovevoley.competitions.models import League, Match, MatchChangeLog
from ilovevoley.core.models import Organization
from ilovevoley.teams.models import Club, Team

User = get_user_model()


class LeagueForTenantTest(TestCase):
    """for_tenant acota las ligas visibles a las del club del tenant."""

    @classmethod
    def setUpTestData(cls):
        cls.club = Club.objects.create(federation_id='c-1', official_name='CV SANT JOSEP')
        cls.own_team = Team.objects.create(name='SANT JOSEP', federation_id='t-1', club=cls.club)
        cls.other_team = Team.objects.create(name='CV ALTRES', federation_id='t-2')

        cls.own_league = League.objects.create(
            name='Lliga pròpia', federation_id='l-1',
            visibility_type='main', is_our_team_related=True, is_active=True,
        )
        cls.other_league = League.objects.create(
            name='Lliga aliena', federation_id='l-2',
            visibility_type='main', is_our_team_related=True, is_active=True,
        )
        Match.objects.create(league=cls.own_league, home_team=cls.own_team, match_date=timezone.now())
        Match.objects.create(league=cls.other_league, home_team=cls.other_team, match_date=timezone.now())

        cls.org_with_club = Organization.objects.create(
            slug='test-with-club', name='Amb club', club=cls.club, club_team_names={'Senior': 'SANT JOSEP'},
        )
        cls.org_without_club = Organization.objects.create(
            slug='test-without-club', name='Sense club', club=None, club_team_names={'Senior': 'BALEARS'},
        )

    def test_tenant_with_club_only_sees_own_leagues(self):
        leagues = League.objects.for_tenant(self.org_with_club)
        self.assertQuerySetEqual(leagues, [self.own_league])

    def test_tenant_without_club_keeps_global_behaviour(self):
        leagues = League.objects.for_tenant(self.org_without_club)
        self.assertQuerySetEqual(leagues, [self.own_league, self.other_league], ordered=False)


class MatchChangeLogTest(TestCase):
    """Pruebas unitarias del modelo MatchChangeLog y su queryset multi-tenant."""

    @classmethod
    def setUpTestData(cls):
        cls.club = Club.objects.create(federation_id='club-1', official_name='CV SANT JOSEP')
        cls.other_club = Club.objects.create(federation_id='club-2', official_name='CV MANACOR')

        cls.team_a = Team.objects.create(name='SANT JOSEP A', federation_id='team-1', club=cls.club)
        cls.team_b = Team.objects.create(name='MANACOR B', federation_id='team-2', club=cls.other_club)
        cls.team_c = Team.objects.create(name='INCA C', federation_id='team-3')

        cls.league = League.objects.create(
            name='1a Balear', federation_id='l-balear',
            visibility_type='main', is_our_team_related=True, is_active=True,
        )
        cls.match_own = Match.objects.create(
            league=cls.league, home_team=cls.team_a, away_team=cls.team_b, match_date=timezone.now()
        )
        cls.match_other = Match.objects.create(
            league=cls.league, home_team=cls.team_b, away_team=cls.team_c, match_date=timezone.now()
        )

        cls.org_with_club = Organization.objects.create(
            slug='sant-josep', name='Sant Josep Org', club=cls.club,
            club_team_names={'Senior': 'SANT JOSEP A'},
        )
        cls.org_without_club = Organization.objects.create(
            slug='fvb', name='Federació Org', club=None, club_team_names={},
        )

        cls.user = User.objects.create_user(username='admin_director', email='director@test.com')

    def test_create_match_change_log_fields(self):
        log = MatchChangeLog.objects.create(
            match=self.match_own,
            change_type='datetime',
            field_name='match_date',
            old_value='2026-10-01 10:00',
            new_value='2026-10-01 12:00',
            is_last_minute=True,
        )
        self.assertIsNotNone(log.id)
        self.assertEqual(log.change_type, 'datetime')
        self.assertEqual(log.field_name, 'match_date')
        self.assertTrue(log.is_last_minute)
        self.assertFalse(log.notified)
        self.assertIsNone(log.notified_at)
        self.assertFalse(log.reviewed)
        self.assertIsNone(log.reviewed_by)
        self.assertIsNone(log.reviewed_at)
        self.assertIsNotNone(log.detected_at)
        self.assertIn('match_date', str(log))

    def test_for_tenant_filters_by_club_matches(self):
        log_own = MatchChangeLog.objects.create(
            match=self.match_own,
            change_type='venue',
            field_name='venue',
            old_value='Pista 1',
            new_value='Pista 2',
        )
        log_other = MatchChangeLog.objects.create(
            match=self.match_other,
            change_type='venue',
            field_name='venue',
            old_value='Pabellón A',
            new_value='Pabellón B',
        )

        # Tenant con club solo ve los logs de partidos de su club
        logs_tenant = MatchChangeLog.objects.for_tenant(self.org_with_club)
        self.assertQuerySetEqual(logs_tenant, [log_own])

        # Tenant sin club mantiene comportamiento global
        logs_global = MatchChangeLog.objects.for_tenant(self.org_without_club)
        self.assertQuerySetEqual(logs_global, [log_own, log_other], ordered=False)

        # Tenant None devuelve none
        self.assertQuerySetEqual(MatchChangeLog.objects.for_tenant(None), [])

