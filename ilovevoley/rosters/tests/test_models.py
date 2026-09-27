from datetime import date

from django.db import IntegrityError
from django.test import TestCase

from ilovevoley.core.models import Organization, Season
from ilovevoley.rosters.models import Person, PlayerRole, StaffRole
from ilovevoley.teams.models import Team


class PersonIdentityConstraintTests(TestCase):
    """La identidad (nombre + fecha de nacimiento) es única dentro de cada organización."""

    def setUp(self):
        self.org_a = Organization.objects.create(slug='org-a', name='Org A')
        self.org_b = Organization.objects.create(slug='org-b', name='Org B')

    def test_misma_persona_en_dos_organizaciones(self):
        Person.objects.create(
            first_name='Ana', last_name='Gomez', birth_date=date(2010, 5, 1),
            organization=self.org_a,
        )
        person_b = Person.objects.create(
            first_name='Ana', last_name='Gomez', birth_date=date(2010, 5, 1),
            organization=self.org_b,
        )
        self.assertEqual(person_b.organization, self.org_b)

    def test_duplicado_en_la_misma_organizacion_falla(self):
        Person.objects.create(
            first_name='Ana', last_name='Gomez', birth_date=date(2010, 5, 1),
            organization=self.org_a,
        )
        with self.assertRaises(IntegrityError):
            Person.objects.create(
                first_name='Ana', last_name='Gomez', birth_date=date(2010, 5, 1),
                organization=self.org_a,
            )

    def test_duplicado_entre_fichas_sin_organizacion_falla(self):
        Person.objects.create(
            first_name='Sin', last_name='Club', birth_date=date(2010, 5, 1),
        )
        with self.assertRaises(IntegrityError):
            Person.objects.create(
                first_name='Sin', last_name='Club', birth_date=date(2010, 5, 1),
            )


class PlayerRoleSeasonConstraintTests(TestCase):
    """Los roles se identifican por temporada: mismo jugador/dorsal en otra temporada es válido."""

    def setUp(self):
        self.org = Organization.objects.create(slug='club', name='Club')
        self.team = Team.objects.create(name='Infantil', federation_id='T-INF')
        self.person = Person.objects.create(
            first_name='Mario', last_name='Perez', organization=self.org,
        )
        self.past = Season.objects.resolve('2025-26')
        self.current = Season.objects.resolve('2026-27')

    def test_mismo_jugador_y_dorsal_en_dos_temporadas(self):
        PlayerRole.objects.create(person=self.person, team=self.team, season=self.past, jersey_number=13)
        PlayerRole.objects.create(person=self.person, team=self.team, season=self.current, jersey_number=13)
        self.assertEqual(self.person.player_roles.count(), 2)

    def test_mismo_jugador_duplicado_en_la_misma_temporada_falla(self):
        PlayerRole.objects.create(person=self.person, team=self.team, season=self.past, jersey_number=7)
        with self.assertRaises(IntegrityError):
            PlayerRole.objects.create(person=self.person, team=self.team, season=self.past, jersey_number=8)

    def test_dorsal_duplicado_en_la_misma_temporada_falla(self):
        other = Person.objects.create(
            first_name='Luis', last_name='Gomez', organization=self.org,
        )
        PlayerRole.objects.create(person=self.person, team=self.team, season=self.past, jersey_number=7)
        with self.assertRaises(IntegrityError):
            PlayerRole.objects.create(person=other, team=self.team, season=self.past, jersey_number=7)


class StaffRoleSeasonConstraintTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(slug='club-s', name='Club S')
        self.team = Team.objects.create(name='Infantil', federation_id='T-INF-S')
        self.person = Person.objects.create(
            first_name='Ana', last_name='Lopez', organization=self.org,
        )
        self.past = Season.objects.resolve('2025-26')
        self.current = Season.objects.resolve('2026-27')

    def test_mismo_rol_en_dos_temporadas(self):
        StaffRole.objects.create(person=self.person, team=self.team, role='head_coach', season=self.past)
        StaffRole.objects.create(person=self.person, team=self.team, role='head_coach', season=self.current)
        self.assertEqual(self.person.staff_roles.count(), 2)

    def test_rol_duplicado_en_la_misma_temporada_falla(self):
        StaffRole.objects.create(person=self.person, team=self.team, role='head_coach', season=self.past)
        with self.assertRaises(IntegrityError):
            StaffRole.objects.create(person=self.person, team=self.team, role='head_coach', season=self.past)

    def test_dos_roles_distintos_en_el_mismo_equipo_y_temporada(self):
        StaffRole.objects.create(person=self.person, team=self.team, role='head_coach', season=self.past)
        StaffRole.objects.create(person=self.person, team=self.team, role='delegate', season=self.past)
        self.assertEqual(self.person.staff_roles.count(), 2)
