from django.test import TestCase
from django.utils import timezone

from ilovevoley.competitions.forms import FriendlyMatchForm, MatchResultForm
from ilovevoley.competitions.models import League, Match
from ilovevoley.core.models import Category, Season
from ilovevoley.teams.models import Team


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


class MatchResultFormSetScoresTest(TestCase):
    """El formulario deriva el marcador de los parciales y los valida."""

    def setUp(self):
        self.league = League.objects.create(
            name='Liga', federation_id='FRM-1', match_format='standard',
            season=Season.objects.resolve('2026-27'),
        )
        self.home = Team.objects.create(name='Local F', federation_id='FRM-H')
        self.away = Team.objects.create(name='Visitante F', federation_id='FRM-A')
        self.match = Match.objects.create(
            league=self.league, home_team=self.home, away_team=self.away,
            match_date=timezone.now(), round_number=1,
        )

    def test_derives_score_from_set_scores(self):
        form = MatchResultForm(
            data={'set_scores': [[25, 20], [25, 18], [25, 22]]},
            instance=self.match,
        )
        self.assertTrue(form.is_valid(), form.errors)
        match = form.save()
        self.assertEqual((match.home_score, match.away_score), (3, 0))
        self.assertEqual(match.set_scores, [[25, 20], [25, 18], [25, 22]])
        self.assertEqual(match.status, 'finished')

    def test_rejects_invalid_partial(self):
        form = MatchResultForm(
            data={'set_scores': [[25, 24], [25, 20], [25, 20]]},
            instance=self.match,
        )
        self.assertFalse(form.is_valid())

    def test_score_without_sets_keeps_existing_behaviour(self):
        form = MatchResultForm(
            data={'home_score': 3, 'away_score': 1},
            instance=self.match,
        )
        self.assertTrue(form.is_valid(), form.errors)
        match = form.save()
        self.assertIsNone(match.set_scores)
        self.assertEqual((match.home_score, match.away_score), (3, 1))

    def test_requires_score_or_sets(self):
        form = MatchResultForm(data={}, instance=self.match)
        self.assertFalse(form.is_valid())

