from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from ilovevoley.competitions.models import League, Match, MatchLineup
from ilovevoley.competitions.services.acta_roster import (
    acta_roster_gaps,
    create_roster_players,
    person_candidates,
)
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.rosters.models import Person, PersonOrganization, PlayerRole
from ilovevoley.teams.models import Club, Team
from ilovevoley.teams.tests.helpers import identity_of


class ActaRosterGapsTests(TestCase):
    """Un hueco mal calculado crea fichas duplicadas de jugadores que ya existen."""

    def setUp(self):
        self.club = Club.objects.create(official_name='Club Test', federation_id='CLUB-T')
        self.org = Organization.objects.create(
            slug='testclub', name='Test Club', club=self.club,
            club_team_names={'1': 'Test Club'}, is_active=True,
        )
        self.category = Category.objects.create(name='Infantil', is_active=True)
        self.team = Team.objects.create(
            name='Test Club Infantil', category=self.category,
            club=self.club, federation_id='TEAM-1', is_active=True,
        )
        self.identity = identity_of(self.team)
        self.rival = Team.objects.create(
            name='Rival Infantil', category=self.category,
            club=Club.objects.create(official_name='Rival', federation_id='CLUB-R'),
            federation_id='TEAM-2', is_active=True,
        )
        self.season = Season.objects.resolve('2025-26')
        self.league = League.objects.create(
            name='Liga Infantil', federation_id='LEAGUE-T', season=self.season,
            is_active=True, visibility_type='main', is_our_team_related=True,
        )
        self.match = Match.objects.create(
            league=self.league, home_team=self.team, away_team=self.rival,
            match_date=timezone.now(), round_number=1, status='finished',
        )
        self.later_match = Match.objects.create(
            league=self.league, home_team=self.team, away_team=self.rival,
            match_date=timezone.now() + timedelta(days=7), round_number=2, status='finished',
        )

    def test_solo_devuelve_dorsales_sin_rol_ni_enlace(self):
        existing = Person.objects.create(first_name='Ana', last_name='Ruiz', birth_year=2012)
        PlayerRole.objects.create(
            person=existing, identity=self.identity, season=self.season,
            jersey_number=9, is_active=True,
        )
        linked = Person.objects.create(first_name='Luis', last_name='Pons', birth_year=2012)

        MatchLineup.objects.create(
            match=self.match, team=self.team, jersey_number=7, name_acta='GARCIA', person=None,
        )
        MatchLineup.objects.create(
            match=self.later_match, team=self.team, jersey_number=7, name_acta='GARCÍA', person=None,
        )
        MatchLineup.objects.create(
            match=self.match, team=self.team, jersey_number=9, name_acta='RUIZ', person=None,
        )
        # Enlace manual a una ficha que no tiene rol con ese dorsal (#570).
        MatchLineup.objects.create(
            match=self.match, team=self.team, jersey_number=11, name_acta='PONS', person=linked,
        )

        gaps = acta_roster_gaps(self.identity, self.season)

        self.assertEqual([gap['jersey_number'] for gap in gaps], [7])
        self.assertEqual(gaps[0]['appearances'], 2)
        # Gana el acta más reciente, que corrige la errata anterior.
        self.assertEqual(gaps[0]['name_acta'], 'GARCÍA')


class CreateRosterPlayersTests(TestCase):
    """Alta de fichas provisionales: efecto persistente y recuperable por filas."""

    def setUp(self):
        self.club = Club.objects.create(official_name='Club Test', federation_id='CLUB-T')
        self.org = Organization.objects.create(
            slug='testclub', name='Test Club', club=self.club,
            club_team_names={'1': 'Test Club'}, is_active=True,
        )
        self.category = Category.objects.create(name='Infantil', is_active=True)
        self.team = Team.objects.create(
            name='Test Club Infantil', category=self.category,
            club=self.club, federation_id='TEAM-1', is_active=True,
        )
        self.identity = identity_of(self.team)
        self.rival = Team.objects.create(
            name='Rival Infantil', category=self.category,
            club=Club.objects.create(official_name='Rival', federation_id='CLUB-R'),
            federation_id='TEAM-2', is_active=True,
        )
        self.season = Season.objects.resolve('2025-26')
        self.league = League.objects.create(
            name='Liga Infantil', federation_id='LEAGUE-T', season=self.season,
            is_active=True, visibility_type='main', is_our_team_related=True,
        )
        self.match = Match.objects.create(
            league=self.league, home_team=self.team, away_team=self.rival,
            match_date=timezone.now(), round_number=1, status='finished',
        )
        self.lineup = MatchLineup.objects.create(
            match=self.match, team=self.team, jersey_number=7, name_acta='GARCIA', person=None,
        )

    def test_crea_provisional_y_enlaza_las_actas_ya_guardadas(self):
        result = create_roster_players(
            self.identity, self.season, self.org,
            [{'jersey': 7, 'last_name': 'García', 'person_id': None}],
        )

        self.assertEqual(result['created'], 1)
        self.assertEqual(result['errors'], [])
        person = Person.objects.get(last_name='García')
        self.assertEqual(person.first_name, '')
        self.assertIsNone(person.birth_year)
        self.assertTrue(person.is_provisional)
        self.assertTrue(
            PersonOrganization.objects.filter(person=person, organization=self.org, is_active=True).exists()
        )
        role = PlayerRole.objects.get(person=person)
        self.assertEqual(role.jersey_number, 7)
        self.assertEqual(role.identity, self.identity)

        # El acta guardada antes del alta no espera a la tarea periódica.
        self.lineup.refresh_from_db()
        self.assertEqual(self.lineup.person, person)

    def test_un_dorsal_ocupado_no_tira_el_resto_del_alta(self):
        other = Person.objects.create(first_name='Ana', last_name='Ruiz', birth_year=2012)
        PlayerRole.objects.create(
            person=other, identity=self.identity, season=self.season,
            jersey_number=9, is_active=True,
        )

        result = create_roster_players(
            self.identity, self.season, self.org,
            [
                {'jersey': 7, 'last_name': 'García', 'person_id': None},
                {'jersey': 9, 'last_name': 'Ruiz', 'person_id': None},
            ],
        )

        self.assertEqual(result['created'], 1)
        self.assertEqual(len(result['errors']), 1)
        self.assertTrue(Person.objects.filter(last_name='García').exists())
        # La fila que falla se revierte entera: no deja una ficha sin rol.
        self.assertFalse(Person.objects.filter(last_name='Ruiz', first_name='').exists())

    def test_reutiliza_una_ficha_existente_sin_marcarla_provisional(self):
        person = Person.objects.create(first_name='Ana', last_name='García', birth_year=2012)
        person.organizations.add(self.org)

        result = create_roster_players(
            self.identity, self.season, self.org,
            [{'jersey': 7, 'last_name': 'Garcia', 'person_id': person.pk}],
        )

        self.assertEqual(result['reused'], 1)
        self.assertEqual(result['created'], 0)
        self.assertFalse(Person.objects.filter(first_name='').exists())
        person.refresh_from_db()
        self.assertFalse(person.is_provisional)
        self.assertEqual(PlayerRole.objects.get(person=person).jersey_number, 7)
        self.assertTrue(
            PersonOrganization.objects.filter(person=person, organization=self.org, is_active=True).exists()
        )

    def test_no_adopta_una_ficha_que_no_casa_con_el_apellido_del_acta(self):
        """El pk del formulario no basta: sin esta regla se adoptaría cualquier ficha."""
        ajena = Person.objects.create(first_name='Otra', last_name='Ruiz', birth_year=2012)

        result = create_roster_players(
            self.identity, self.season, self.org,
            [{'jersey': 7, 'last_name': 'García', 'person_id': ajena.pk}],
        )

        self.assertEqual(result['reused'], 0)
        self.assertEqual(result['created'], 0)
        self.assertEqual(len(result['errors']), 1)
        self.assertFalse(PlayerRole.objects.filter(person=ajena).exists())
        self.assertFalse(
            PersonOrganization.objects.filter(person=ajena, organization=self.org).exists()
        )

    def test_no_adopta_una_ficha_de_otro_club_aunque_coincida_el_apellido(self):
        """Aislar clubes: aunque el apellido case, una ficha ajena no se adopta por aquí."""
        other_org = Organization.objects.create(slug='otro', name='Otro Club', is_active=True)
        ajena = Person.objects.create(first_name='Otra', last_name='García', birth_year=2012)
        ajena.organizations.add(other_org)

        result = create_roster_players(
            self.identity, self.season, self.org,
            [{'jersey': 7, 'last_name': 'García', 'person_id': ajena.pk}],
        )

        self.assertEqual(result['reused'], 0)
        self.assertEqual(len(result['errors']), 1)
        self.assertFalse(
            PersonOrganization.objects.filter(person=ajena, organization=self.org).exists()
        )

    def test_los_candidatos_son_solo_del_club(self):
        other_org = Organization.objects.create(slug='otro', name='Otro Club', is_active=True)
        ajena = Person.objects.create(first_name='Otra', last_name='García', birth_year=2012)
        ajena.organizations.add(other_org)
        propia = Person.objects.create(first_name='Ana', last_name='García', birth_year=2012)
        propia.organizations.add(self.org)

        candidatos = person_candidates('GARCIA', self.org)

        self.assertEqual([c['person'] for c in candidatos], [propia])

    def test_apellido_demasiado_largo_se_rechaza_sin_abortar_el_alta(self):
        result = create_roster_players(
            self.identity, self.season, self.org,
            [
                {'jersey': 7, 'last_name': 'X' * 101, 'person_id': None},
                {'jersey': 8, 'last_name': 'Pons', 'person_id': None},
            ],
        )

        self.assertEqual(result['created'], 1)
        self.assertEqual(len(result['errors']), 1)
        self.assertTrue(Person.objects.filter(last_name='Pons').exists())
