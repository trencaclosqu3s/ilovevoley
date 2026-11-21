"""Datos compartidos por los tests de competitions."""

from datetime import timedelta

from django.utils import timezone

from ilovevoley.competitions.models import League, Match
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.teams.models import Club, Team


def setup_live_match(test):
    """Club, liga y un partido dentro de la ventana de directo, como atributos de ``test``."""
    test.club = Club.objects.create(official_name='Sant Just', federation_id='SJ01')
    test.org = Organization.objects.create(
        name='CV Sant Just', slug='santjust', club=test.club
    )
    test.season = Season.objects.create(name='2025-26', start_year=2025, is_current=True)
    test.category = Category.objects.create(name='Senior Femenino')
    test.team1 = Team.objects.create(
        name='Senior A', club=test.club, federation_id='T01', category=test.category
    )
    test.team2 = Team.objects.create(name='Rival B', federation_id='T02')
    test.league = League.objects.create(name='1a Balear', season=test.season)
    test.league.categories.add(test.category)

    # Partido dentro de la ventana de directo (en 15 minutos)
    test.match = Match.objects.create(
        league=test.league,
        home_team=test.team1,
        away_team=test.team2,
        match_date=timezone.now() + timedelta(minutes=15),
        status='scheduled',
        stream_url='https://www.youtube.com/watch?v=live123',
    )
