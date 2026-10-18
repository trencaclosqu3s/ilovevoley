"""Vínculo manual entre una entrada del acta y un deportista de la plantilla.

Cubre el endpoint que lo gestiona: permisos, alcance al club propio y efecto
persistente sobre ``MatchLineup`` (la estadística del jugador).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ilovevoley.competitions.models import (
    League, Match, MatchLineup, MatchLineupPersonLink,
)
from ilovevoley.competitions.services.lineups import store_match_lineups
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.rosters.models import Person, PlayerRole
from ilovevoley.teams.models import Club, Team
from ilovevoley.teams.tests.helpers import identity_of
from ilovevoley.users.models import Membership


def _entry(position, number):
    return {'position': position, 'number': number, 'sub': None}


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'])
class ActaPersonLinkEndpointTests(TestCase):
    def setUp(self):
        self.club = Club.objects.create(official_name='Club Test', federation_id='CLUB-T')
        self.org = Organization.objects.create(
            slug='testclub', name='Test Club', club=self.club, is_active=True,
        )
        self.category = Category.objects.create(name='Senior', is_active=True)
        self.team = Team.objects.create(
            name='Test Club Senior', category=self.category, club=self.club,
            federation_id='TEAM-1', is_active=True,
        )
        self.rival = Team.objects.create(
            name='Rival Team Senior', category=self.category,
            club=Club.objects.create(official_name='Rival', federation_id='CLUB-R'),
            federation_id='TEAM-2', is_active=True,
        )
        self.season = Season.objects.resolve('2025-26')
        self.league = League.objects.create(
            name='Superliga 2', federation_id='LEAGUE-T', season=self.season,
            is_active=True, visibility_type='main', is_our_team_related=True,
        )
        self.match = Match.objects.create(
            league=self.league, home_team=self.team, away_team=self.rival,
            match_date=timezone.now(), round_number=1, status='finished',
            acta_html='https://federacion.example/acta/1',
        )

        self.ficha = Person.objects.create(first_name='Ficha', last_name='Cuatro')
        self.ficha.organizations.add(self.org)
        PlayerRole.objects.create(
            person=self.ficha, identity=identity_of(self.team), season=self.season,
            jersey_number=4, is_active=True,
        )
        self.vinculada = Person.objects.create(first_name='Vinculada', last_name='Otra')
        self.vinculada.organizations.add(self.org)

        store_match_lineups(self.match, {
            'home_team': 'Test Club Senior',
            'away_team': 'Rival Team Senior',
            'home_convocados': ['4 Cuatro', '14 Otra'],
            'away_convocados': [],
            'sets': [{
                'title': 'Set 1',
                'time': '',
                'teams': [
                    {'name': 'Test Club Senior', 'points': 25, 'lineup': [
                        _entry('I', 4), _entry('II', 14), _entry('III', 2),
                        _entry('IV', 3), _entry('V', 5), _entry('VI', 6),
                    ]},
                    {'name': 'Rival Team Senior', 'points': 20, 'lineup': []},
                ],
            }],
        })

        User = get_user_model()
        self.manager = User.objects.create_user(username='manager', password='pass')
        Membership.objects.create(
            user=self.manager, organization=self.org, is_approved=True, role='manager',
        )
        self.member = User.objects.create_user(username='member', password='pass')
        Membership.objects.create(
            user=self.member, organization=self.org, is_approved=True, role='member',
        )
        self.url = reverse('competitions:ajax_link_acta_person', args=[self.match.id])

    def _row(self, jersey):
        return MatchLineup.objects.get(match=self.match, team=self.team, jersey_number=jersey)

    def test_manager_vincula_dorsal_del_acta_con_la_persona_correcta(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            self.url,
            {'team_id': self.team.id, 'jersey_number': 14, 'person_id': self.vinculada.id},
            HTTP_HOST='testclub.ilovevoley.es',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.assertEqual(response.json()['person']['id'], self.vinculada.id)
        self.assertEqual(self._row(14).person_id, self.vinculada.id)
        self.assertTrue(
            MatchLineupPersonLink.objects.filter(
                match=self.match, team=self.team, jersey_number=14, person=self.vinculada,
            ).exists()
        )

    def test_miembro_sin_permiso_no_puede_vincular(self):
        self.client.force_login(self.member)
        response = self.client.post(
            self.url,
            {'team_id': self.team.id, 'jersey_number': 14, 'person_id': self.vinculada.id},
            HTTP_HOST='testclub.ilovevoley.es',
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(MatchLineupPersonLink.objects.filter(match=self.match).exists())
        self.assertIsNone(self._row(14).person_id)

    def test_no_puede_vincular_un_equipo_de_otro_club(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            self.url,
            {'team_id': self.rival.id, 'jersey_number': 7, 'person_id': self.vinculada.id},
            HTTP_HOST='testclub.ilovevoley.es',
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(MatchLineupPersonLink.objects.filter(match=self.match).exists())

    def test_desvincular_devuelve_el_dorsal_a_su_dueno(self):
        self.client.force_login(self.manager)
        self.client.post(
            self.url,
            {'team_id': self.team.id, 'jersey_number': 4, 'person_id': self.vinculada.id},
            HTTP_HOST='testclub.ilovevoley.es',
        )
        self.assertEqual(self._row(4).person_id, self.vinculada.id)

        response = self.client.post(
            self.url,
            {'team_id': self.team.id, 'jersey_number': 4, 'person_id': ''},
            HTTP_HOST='testclub.ilovevoley.es',
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(MatchLineupPersonLink.objects.filter(match=self.match).exists())
        self.assertEqual(self._row(4).person_id, self.ficha.id)

    def test_el_control_de_vincular_solo_aparece_para_managers(self):
        # El bloque de acta del detalle solo se renderiza con acta_html; este
        # test lo ejercita y comprueba que el permiso llega a la plantilla.
        detail_url = reverse('competitions:match_detail', args=[self.match.id])
        self.client.force_login(self.manager)
        manager_page = self.client.get(detail_url, HTTP_HOST='testclub.ilovevoley.es').content.decode()
        self.assertIn('var canEditActa = true', manager_page)

        self.client.force_login(self.member)
        member_page = self.client.get(detail_url, HTTP_HOST='testclub.ilovevoley.es').content.decode()
        self.assertIn('var canEditActa = false', member_page)
