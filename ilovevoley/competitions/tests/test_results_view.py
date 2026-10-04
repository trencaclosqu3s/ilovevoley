from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ilovevoley.competitions.models import League, Match
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.teams.models import Club, Team
from ilovevoley.users.models import CategoryPreference, Membership

HOST = 'testclub.ilovevoley.es'


@override_settings(ALLOWED_HOSTS=[HOST, 'localhost'])
class ResultsViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.org = Organization.objects.create(
            slug='testclub', name='Test Club',
            club_team_names={'1': 'Test Club'}, is_active=True,
        )
        self.user = get_user_model().objects.create_user(username='member', password='pass')
        Membership.objects.create(
            user=self.user, organization=self.org, is_approved=True, role='member',
        )
        self.senior = Category.objects.create(name='Senior', is_active=True)
        self.junior = Category.objects.create(name='Junior', is_active=True)
        self.season = Season.objects.resolve('2026-2027')
        self.club = Club.objects.create(official_name='Club Test', federation_id='C1')
        self.ours_senior = Team.objects.create(
            name='Test Club Senior', category=self.senior, club=self.club,
            federation_id='T1', is_active=True,
        )
        self.ours_junior = Team.objects.create(
            name='Test Club Junior', category=self.junior, club=self.club,
            federation_id='T2', is_active=True,
        )
        self.rival_a = Team.objects.create(
            name='Rival A', category=self.senior, federation_id='T3', is_active=True,
        )
        self.rival_b = Team.objects.create(
            name='Rival B', category=self.junior, federation_id='T4', is_active=True,
        )
        self.league_senior = League.objects.create(
            name='Liga Senior', federation_id='L1', season=self.season, is_active=True,
        )
        self.league_senior.categories.add(self.senior)
        self.league_junior = League.objects.create(
            name='Liga Junior', federation_id='L2', season=self.season, is_active=True,
        )
        self.league_junior.categories.add(self.junior)
        self.client.force_login(self.user)

    def _match(self, home, away, league, days_ago=1, **kwargs):
        kwargs.setdefault('status', 'finished')
        kwargs.setdefault('home_score', 3)
        kwargs.setdefault('away_score', 1)
        return Match.objects.create(
            league=league, home_team=home, away_team=away,
            match_date=timezone.now() - timedelta(days=days_ago), **kwargs,
        )

    def _get(self, **params):
        params.setdefault('season', self.season.pk)
        response = self.client.get(reverse('competitions:results_view'), params, HTTP_HOST=HOST)
        self.assertEqual(response.status_code, 200)
        return response, list(response.context['matches'])

    def test_default_shows_only_club_matches_within_user_categories(self):
        ours_senior = self._match(self.ours_senior, self.rival_a, self.league_senior)
        ours_junior = self._match(self.rival_b, self.ours_junior, self.league_junior)
        others = self._match(self.rival_a, self.rival_b, self.league_senior)
        CategoryPreference.objects.create(
            user=self.user, organization=self.org,
        ).categories.add(self.senior)

        _, matches = self._get()
        self.assertEqual(matches, [ours_senior])

        # Cualquier filtro explícito levanta las restricciones por defecto.
        _, matches = self._get(all_teams='1')
        self.assertCountEqual(matches, [ours_senior, ours_junior, others])
        _, matches = self._get(teams=[self.rival_b.pk])
        self.assertCountEqual(matches, [ours_junior, others])
        _, matches = self._get(teams=[self.rival_a.pk, self.rival_b.pk])
        self.assertCountEqual(matches, [ours_senior, ours_junior, others])
        _, matches = self._get(all_teams='1', category=self.junior.pk)
        self.assertCountEqual(matches, [ours_junior])

    def test_only_finished_matches_and_period_cuts(self):
        recent = self._match(self.ours_senior, self.rival_a, self.league_senior, days_ago=2)
        old = self._match(self.ours_senior, self.rival_a, self.league_senior, days_ago=60)
        self._match(self.ours_senior, self.rival_a, self.league_senior, status='scheduled',
                    home_score=None, away_score=None)
        self._match(self.ours_senior, self.rival_a, self.league_senior, status='withdrawn')

        _, matches = self._get(period='season')
        self.assertEqual(matches, [recent, old])  # más reciente primero
        _, matches = self._get(period='month')
        self.assertEqual(matches, [recent])

    def test_team_search_returns_teams_from_other_clubs(self):
        response = self.client.get(
            reverse('competitions:ajax_results_teams'), {'q': 'rival'}, HTTP_HOST=HOST,
        )
        self.assertEqual(response.status_code, 200)
        names = {t['name'] for t in response.json()['teams']}
        self.assertEqual(names, {'Rival A', 'Rival B'})
