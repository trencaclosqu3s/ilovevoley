from django.db import IntegrityError
from django.test import TestCase

from videosvoley.core.models import Season
from videosvoley.rosters.models import Person, PlayerRole, StaffRole
from videosvoley.teams.models import Team


class PlayerRoleSeasonConstraintTests(TestCase):
    """Los roles se identifican por temporada: mismo jugador/dorsal en otra temporada es válido."""

    def setUp(self):
        self.team = Team.objects.create(name='Infantil', federation_id='T-INF')
        self.person = Person.objects.create(first_name='Mario', last_name='Perez')
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
        other = Person.objects.create(first_name='Luis', last_name='Gomez')
        PlayerRole.objects.create(person=self.person, team=self.team, season=self.past, jersey_number=7)
        with self.assertRaises(IntegrityError):
            PlayerRole.objects.create(person=other, team=self.team, season=self.past, jersey_number=7)


class StaffRoleSeasonConstraintTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name='Infantil', federation_id='T-INF-S')
        self.person = Person.objects.create(first_name='Ana', last_name='Lopez')
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
