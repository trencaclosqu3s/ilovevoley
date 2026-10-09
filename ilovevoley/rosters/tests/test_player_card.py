from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ilovevoley.competitions.models import League, Match
from ilovevoley.competitions.services.lineups import store_match_lineups
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.rosters.models import Person, PlayerRole
from ilovevoley.rosters.player_card import card_highlight, pick_profile, season_facts
from ilovevoley.teams.models import Club, Team
from ilovevoley.teams.tests.helpers import identity_of
from ilovevoley.users.models import Membership

JERSEY = 7


def _entry(position, number, sub=None):
    return {'position': position, 'number': number, 'sub': {'number': sub} if sub else None}


def _lineup(with_player=True, sub_for=None):
    """Seis en pista: con ``with_player`` el #7 es titular; con ``sub_for`` entra por ese dorsal."""
    numbers = [JERSEY, 2, 3, 4, 5, 6] if with_player else [1, 2, 3, 4, 5, 6]
    return [
        _entry(pos, n, sub=JERSEY if n == sub_for else None)
        for pos, n in zip(('I', 'II', 'III', 'IV', 'V', 'VI'), numbers)
    ]


class PlayerCardTestBase(TestCase):
    def setUp(self):
        cache.clear()
        self.club = Club.objects.create(official_name='Club Test', federation_id='CLUB-T')
        self.org = Organization.objects.create(
            slug='testclub', name='Test Club', club=self.club,
            club_team_names={'1': 'Test Club'}, is_active=True,
        )
        category = Category.objects.create(name='Cadete', is_active=True)
        self.team = Team.objects.create(
            name='Test Club Cadete', category=category, club=self.club, federation_id='TEAM-1', is_active=True,
        )
        self.rival = Team.objects.create(
            name='Rival Cadete', category=category,
            club=Club.objects.create(official_name='Rival', federation_id='CLUB-R'),
            federation_id='TEAM-2', is_active=True,
        )
        self.season = Season.objects.resolve('2025-26')
        self.league = League.objects.create(
            name='Liga Cadete', federation_id='LEAGUE-T', season=self.season,
            is_active=True, visibility_type='main', is_our_team_related=True,
        )
        self.person = Person.objects.create(first_name='Marc', last_name='Ferrer', birth_year=2011)
        self.person.organizations.add(self.org)
        PlayerRole.objects.create(
            person=self.person, identity=identity_of(self.team), season=self.season,
            jersey_number=JERSEY, position='setter', is_active=True,
        )
        self.round = 0

    def play(self, sets):
        """Partido en casa con acta. ``sets`` = [(nuestros, suyos, alineación), ...]."""
        self.round += 1
        won = sum(ours > theirs for ours, theirs, _ in sets)
        match = Match.objects.create(
            league=self.league, home_team=self.team, away_team=self.rival, round_number=self.round,
            match_date=timezone.now() - timedelta(days=30 - self.round), status='finished',
            home_score=won, away_score=len(sets) - won,
        )
        store_match_lineups(match, {
            'home_team': self.team.name, 'away_team': self.rival.name,
            'home_convocados': [f'{JERSEY} Marc Ferrer'], 'away_convocados': [],
            'sets': [
                {'title': f'Set {i}', 'teams': [
                    {'name': self.team.name, 'points': ours, 'lineup': lineup},
                    {'name': self.rival.name, 'points': theirs, 'lineup': _lineup(False)},
                ]}
                for i, (ours, theirs, lineup) in enumerate(sets, 1)
            ],
        })
        return match

    def highlight(self):
        return card_highlight(self.person, [self.team], self.season)


class PlayerCardProfileTests(PlayerCardTestBase):
    """El perfil tiene que ser cierto: quien lo recibe sabe cuánto ha jugado."""

    def test_lesionado_media_temporada_no_sale_fijo_sino_momento(self):
        # Titular en todo lo que jugó, pero solo 1 de 4 partidos: no es "fijo en el seis".
        self.play([(25, 15, _lineup())] * 3)
        for _ in range(3):
            self.play([(25, 15, _lineup(False))] * 3)

        facts = season_facts(self.person, [self.team], self.season)
        self.assertEqual((facts['starts'], facts['team_sets']), (3, 12))
        self.assertIsNone(pick_profile(facts))
        highlight = self.highlight()
        self.assertEqual(highlight['key'], 'momento')
        self.assertEqual(highlight['title'], 'Victoria 3-0')

    def test_talisman_gana_a_sangre_fria(self):
        # Con él: 15 sets ganados por la mínima. Sin él: el equipo pierde 9.
        for _ in range(5):
            self.play([(25, 23, _lineup())] * 3)
        for _ in range(3):
            self.play([(15, 25, _lineup(False))] * 3)

        self.assertEqual(self.highlight()['key'], 'talisman')

    def test_entrar_de_cambio_cuenta_como_revulsivo_no_como_titular(self):
        for _ in range(5):
            self.play([(25, 18, _lineup(False, sub_for=4))] + [(25, 10, _lineup(False))] * 2)

        facts = season_facts(self.person, [self.team], self.season)
        self.assertEqual((facts['sub_sets'], facts['starts']), (5, 0))
        self.assertEqual(self.highlight()['key'], 'revulsivo')


@override_settings(ALLOWED_HOSTS=['testclub.ilovevoley.es', 'localhost'])
class PlayerCardViewTests(PlayerCardTestBase):
    """Es la imagen de un menor para redes: solo la familia, él mismo o los gestores."""

    def setUp(self):
        super().setUp()
        self.url = reverse('rosters:person_card', args=[self.person.id])

    def member(self, username):
        user = get_user_model().objects.create_user(username=username, password='pass')
        Membership.objects.create(user=user, organization=self.org, is_approved=True)
        self.client.force_login(user)
        return user

    def test_padre_descarga_el_cromo_de_su_hijo(self):
        self.play([(25, 20, _lineup())] * 3)
        self.member('padre').children.add(self.person)

        response = self.client.get(self.url, HTTP_HOST='testclub.ilovevoley.es')

        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertTrue(response.content.startswith(b'\x89PNG'))

    def test_otro_socio_del_club_no_puede_generarlo(self):
        self.member('socio')

        response = self.client.get(self.url, HTTP_HOST='testclub.ilovevoley.es')

        self.assertEqual(response.status_code, 403)

    def test_padre_sin_ficha_propia_ve_el_cromo_de_su_hijo_en_tu(self):
        self.member('padre').children.add(self.person)

        response = self.client.get(reverse('rosters:my_profile'), HTTP_HOST='testclub.ilovevoley.es')

        self.assertContains(response, self.url)
