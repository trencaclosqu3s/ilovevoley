from django.contrib import admin as django_admin
from django.test import TestCase
from django.utils import timezone

from ilovevoley.competitions.models import League, Match
from ilovevoley.core.admin import OrganizationAdmin
from ilovevoley.core.models import Organization, Season
from ilovevoley.teams.models import Club, Team


class OrganizationAdminClubHelpersTest(TestCase):
    def setUp(self):
        self.admin = OrganizationAdmin(Organization, django_admin.site)
        self.club = Club.objects.create(federation_id='c-1', official_name='CLUB ESPORTIU SANT JOSEP OBRER')
        self.org = Organization.objects.create(
            slug='test-org', name='Test', club=self.club,
            club_team_names={'Senior': 'SANT JOSEP'},
        )

    def test_club_teams_count_counts_active_teams(self):
        Team.objects.create(name='SANT JOSEP A', federation_id='t-1', club=self.club, is_active=True)
        Team.objects.create(name='SANT JOSEP B', federation_id='t-2', club=self.club, is_active=False)
        self.assertEqual(self.admin.club_teams_count(self.org), 1)

    def test_club_names_status_flags_mismatch(self):
        Team.objects.create(name='EQUIP FORA', federation_id='t-3', club=self.club)
        self.assertIn('no casa', self.admin.club_names_status(self.org))

    def test_club_names_status_treats_blank_names_as_missing(self):
        org = Organization.objects.create(
            slug='test-blank', name='Blank', club=self.club, club_team_names={'Senior': ''},
        )
        Team.objects.create(name='CV SANT JOSEP', federation_id='t-6', club=self.club)
        self.assertIn('Sin club_team_names', self.admin.club_names_status(org))

    def test_assign_club_action_fills_orphan_teams_by_match_club_ids(self):
        """Asigna por el id de club de los partidos, no por el nombre (#380)."""
        orphan = Team.objects.create(name='PORTOL ROJO', federation_id='t-4', club=None)
        unrelated = Team.objects.create(name='SANT JOSEP OBRER B', federation_id='t-5', club=None)
        league = League.objects.create(
            name='Liga', federation_id='1', season=Season.objects.resolve('2026-27'),
            competition_type='regular', match_format='standard', visibility_type='main',
        )
        Match.objects.create(
            league=league, home_team=orphan, away_team=unrelated, match_date=timezone.now(),
            federation_club_local_id='c-1', federation_club_away_id='c-2',
        )
        self.admin.message_user = lambda *args, **kwargs: None

        self.admin.assign_club_to_orphan_teams(None, Organization.objects.filter(pk=self.org.pk))

        orphan.refresh_from_db()
        unrelated.refresh_from_db()
        self.assertEqual(orphan.club_id, self.club.id)
        self.assertIsNone(unrelated.club_id)
