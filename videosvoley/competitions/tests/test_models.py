from django.test import TestCase
from django.utils import timezone

from videosvoley.competitions.models import League, Match
from videosvoley.core.models import Organization
from videosvoley.teams.models import Club, Team


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
