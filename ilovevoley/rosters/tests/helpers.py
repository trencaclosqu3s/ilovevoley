"""Base y datos compartidos de los tests de la tarjeta de jugador y del Wrapped."""

from datetime import timedelta
from io import BytesIO

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from PIL import Image as PILImage

from ilovevoley.competitions.models import League, Match
from ilovevoley.competitions.services.lineups import store_match_lineups
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.rosters.models import Person, PlayerRole
from ilovevoley.rosters.player_card import card_highlight
from ilovevoley.teams.models import Club, Team
from ilovevoley.teams.tests.helpers import identity_of


JERSEY = 7


def _png():
    buffer = BytesIO()
    PILImage.new('RGB', (4, 4)).save(buffer, 'PNG')
    return buffer.getvalue()


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
