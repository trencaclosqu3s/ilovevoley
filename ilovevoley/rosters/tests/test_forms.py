from django.test import TestCase

from ilovevoley.core.models import Organization, Season
from ilovevoley.rosters.forms import PlayerRoleForm, StaffRoleForm
from ilovevoley.rosters.models import Person, PlayerRole, StaffRole
from ilovevoley.teams.models import Team


class RoleFormDuplicateValidationTests(TestCase):
    """El formulario debe dar error de validación, no un IntegrityError de BD."""

    def setUp(self):
        self.org = Organization.objects.create(
            slug='club', name='Club', club_team_names={'1': 'Club'},
        )
        self.team = Team.objects.create(name='Club Senior', federation_id='T-F')
        self.person = Person.objects.create(
            first_name='Ana', last_name='Gomez', organization=self.org,
        )
        self.season = Season.objects.resolve('2025-26')

    def test_staff_role_duplicado_no_valida(self):
        StaffRole.objects.create(
            person=self.person, team=self.team, role='head_coach', season=self.season,
        )
        form = StaffRoleForm(
            data={'team': self.team.id, 'season': self.season.id, 'role': 'head_coach'},
            person=self.person, organization=self.org,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('__all__', form.errors)

    def test_player_role_duplicado_no_valida(self):
        PlayerRole.objects.create(
            person=self.person, team=self.team, season=self.season, jersey_number=7,
        )
        form = PlayerRoleForm(
            data={'team': self.team.id, 'season': self.season.id, 'jersey_number': 8},
            person=self.person, organization=self.org,
        )
        self.assertFalse(form.is_valid())
        # El equipo con rol activo en esa temporada se excluye del queryset.
        self.assertIn('team', form.errors)
