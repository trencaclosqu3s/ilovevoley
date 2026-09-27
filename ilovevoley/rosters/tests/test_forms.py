from datetime import date

from django.test import TestCase

from ilovevoley.core.models import Organization, Season
from ilovevoley.rosters.forms import PersonForm, PlayerRoleForm, StaffRoleForm
from ilovevoley.rosters.models import Person, PlayerRole, StaffRole
from ilovevoley.teams.models import Team


class PersonFormIdentityValidationTests(TestCase):
    """El alta valida la identidad contra el tenant, no globalmente."""

    def setUp(self):
        self.org_a = Organization.objects.create(slug='org-a', name='Org A')
        self.org_b = Organization.objects.create(slug='org-b', name='Org B')
        self.person_a = Person.objects.create(
            first_name='Ana', last_name='Gomez', birth_date=date(2010, 5, 1),
            organization=self.org_a,
        )
        self.data = {
            'first_name': 'Ana',
            'last_name': 'Gomez',
            'birth_date': '2010-05-01',
        }

    def test_misma_identidad_en_otra_organizacion_es_valida(self):
        form = PersonForm(data=self.data, organization=self.org_b)
        self.assertTrue(form.is_valid(), form.errors)

    def test_duplicado_en_la_misma_organizacion_no_valida(self):
        form = PersonForm(data=self.data, organization=self.org_a)
        self.assertFalse(form.is_valid())

    def test_edicion_sin_cambiar_identidad_es_valida(self):
        form = PersonForm(
            data=self.data, instance=self.person_a, organization=self.org_a,
        )
        self.assertTrue(form.is_valid(), form.errors)


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
