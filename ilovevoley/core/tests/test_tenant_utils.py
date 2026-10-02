from django.test import TestCase

from ilovevoley.core.models import Organization
from ilovevoley.core.tenant_utils import team_belongs_to_tenant
from ilovevoley.teams.models import Club, Team


class TeamBelongsToTenantTests(TestCase):
    def test_orphan_team_without_club_denied_access(self):
        club = Club.objects.create(
            official_name='Club Voleibol Test', federation_id='CLUB-TEST',
        )
        org = Organization.objects.create(
            slug='testclub', name='Test Club', club=club, is_active=True,
        )
        orphan_team = Team.objects.create(
            name='Test Club Huérfano',
            club=None,
            federation_id='TEAM-ORPHAN-1',
            is_active=True,
        )
        self.assertFalse(team_belongs_to_tenant(orphan_team, org))
