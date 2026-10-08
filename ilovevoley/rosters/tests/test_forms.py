from datetime import date

from django.test import TestCase

from ilovevoley.competitions.models import League, Standing
from ilovevoley.core.models import Organization, Season
from ilovevoley.rosters.forms import PersonForm, PlayerRoleForm, StaffRoleForm, _club_teams_for_seasons
from ilovevoley.rosters.models import Person, PlayerRole, StaffRole
from ilovevoley.teams.models import Team


class PersonFormIdentityValidationTests(TestCase):
    """La identidad (nombre + año de nacimiento) es global, no por club."""

    def setUp(self):
        self.person_a = Person.objects.create(
            first_name='Ana', last_name='Gomez', birth_date=date(2010, 5, 1),
        )
        self.data = {
            'first_name': 'Ana',
            'last_name': 'Gomez',
            'birth_date': '2010-05-01',
        }

    def test_misma_identidad_es_duplicado_y_expone_la_ficha_existente(self):
        # La vista usa existing_person() para ofrecer "Añadir a mi club".
        form = PersonForm(data=self.data)
        self.assertFalse(form.is_valid())
        self.assertEqual(form.existing_person(), self.person_a)

    def test_edicion_sin_cambiar_identidad_es_valida(self):
        form = PersonForm(data=self.data, instance=self.person_a)
        self.assertTrue(form.is_valid(), form.errors)

    def test_sin_fecha_el_año_es_obligatorio(self):
        data = {'first_name': 'Eva', 'last_name': 'Sola'}
        self.assertIn('birth_year', PersonForm(data=data).errors)
        self.assertTrue(PersonForm(data={**data, 'birth_year': '2012'}).is_valid())


class RoleFormDuplicateValidationTests(TestCase):
    """El formulario debe dar error de validación, no un IntegrityError de BD."""

    def setUp(self):
        self.org = Organization.objects.create(
            slug='club', name='Club', club_team_names={'1': 'Club'},
        )
        self.team = Team.objects.create(name='Club Senior', federation_id='T-F')
        self.person = Person.objects.create(first_name='Ana', last_name='Gomez')
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


class RoleFormTeamChoicesTests(TestCase):
    """El selector de equipo solo ofrece equipos con presencia en la temporada (#445)."""

    def setUp(self):
        self.org = Organization.objects.create(
            slug='club', name='Club', club_team_names={'1': 'Club'},
        )
        self.season = Season.objects.resolve('2026-27')
        Season.objects.filter(pk=self.season.pk).update(is_current=True)
        old_season = Season.objects.resolve('2025-26')
        self.current = Team.objects.create(name='Club Senior', federation_id='T-CUR')
        self.old = Team.objects.create(name='Club Senior', federation_id='T-OLD')
        for team, season in ((self.current, self.season), (self.old, old_season)):
            league = League.objects.create(name=f'L {team.federation_id}', federation_id=team.federation_id, season=season)
            Standing.objects.create(league=league, team=team, position=1)

    def test_no_ofrece_equipos_de_otras_temporadas(self):
        form = PlayerRoleForm(organization=self.org)
        self.assertEqual(list(form.fields['team'].queryset), [self.current])

    def test_temporada_sin_presencia_ofrece_todos_los_equipos_activos(self):
        # Temporada recién creada y sin scrapear (#344): hay que poder prepararla.
        empty = Season.objects.resolve('2027-28')
        teams = _club_teams_for_seasons(self.org, [empty])
        self.assertEqual(set(teams), {self.current, self.old})
