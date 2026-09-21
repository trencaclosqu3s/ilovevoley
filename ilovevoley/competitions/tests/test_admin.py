from django.contrib import admin as django_admin
from django.test import TestCase
from django.utils import timezone

from ilovevoley.competitions.admin.competitions import LeagueAdmin
from ilovevoley.competitions.models import League, Match
from ilovevoley.core.models import Organization
from ilovevoley.teams.models import Club, Team


class LeagueRelatedOrganizationsTest(TestCase):
    """La detección FK + string alimenta el aviso de is_our_team_related."""

    @classmethod
    def setUpTestData(cls):
        cls.club = Club.objects.create(federation_id='c-1', official_name='CV SANT JOSEP')
        cls.org = Organization.objects.create(
            slug='test-org', name='Test', club=cls.club, club_team_names={'Senior': 'SANT JOSEP'},
        )

    def setUp(self):
        self.admin = LeagueAdmin(League, django_admin.site)

    def _league_with_team(self, team, fed_id):
        league = League.objects.create(name=f'Lliga {fed_id}', federation_id=fed_id)
        Match.objects.create(league=league, home_team=team, match_date=timezone.now())
        return league

    def test_detects_organization_by_club_fk(self):
        team = Team.objects.create(name='BAR BINI SOLLER', federation_id='t-1', club=self.club)
        league = self._league_with_team(team, 'l-1')
        self.assertIn('test-org', self.admin.related_organizations(league))

    def test_detects_organization_by_orphan_name(self):
        team = Team.objects.create(name='CV SANT JOSEP B', federation_id='t-2', club=None)
        league = self._league_with_team(team, 'l-2')
        self.assertIn('test-org', self.admin.related_organizations(league))

    def test_no_organization_when_unrelated(self):
        team = Team.objects.create(name='CV ALTRES', federation_id='t-3')
        league = self._league_with_team(team, 'l-3')
        self.assertIn('Ninguna', self.admin.related_organizations(league))
