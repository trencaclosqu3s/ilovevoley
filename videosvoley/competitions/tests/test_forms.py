from django.test import TestCase
from django.utils import timezone

from videosvoley.competitions.forms import FriendlyMatchForm
from videosvoley.competitions.models import League
from videosvoley.core.models import Category, Season
from videosvoley.teams.models import Team


class FriendlyMatchLeagueTest(TestCase):
    """La liga de amistosos debe reutilizarse por federación, no duplicarse por nombre."""

    def test_reutiliza_la_liga_amistosa_en_la_temporada_activa(self):
        category = Category.objects.create(name='Senior Test')
        home = Team.objects.create(name='Local', federation_id='FM-H')
        away = Team.objects.create(name='Visitante', federation_id='FM-A')
        data = {
            'match_date': timezone.now().strftime('%Y-%m-%dT%H:%M'),
            'home_team_id': home.id,
            'away_team_id': away.id,
            'category': category.id,
        }

        for _ in range(2):
            form = FriendlyMatchForm(data=data)
            self.assertTrue(form.is_valid(), form.errors)
            form.save()

        ligas = League.objects.filter(competition_type='friendly', categories=category)
        self.assertEqual(ligas.count(), 1)
        self.assertEqual(ligas.first().season_id, Season.objects.for_date(timezone.now()).pk)
