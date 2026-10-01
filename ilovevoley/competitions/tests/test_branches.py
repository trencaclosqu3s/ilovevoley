from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from ilovevoley.competitions.models import League, Match
from ilovevoley.competitions.services.branches import match_branches, organization_branch_q
from ilovevoley.core.models import (
    GENDER_FEMALE,
    GENDER_MALE,
    GENDER_MIXED,
    Category,
    Organization,
    Season,
)
from ilovevoley.teams.models import Club, Team


class MatchBranchesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.season = Season.objects.create(name='2026-27', start_year=2026, end_year=2027, is_current=True)
        cls.club = Club.objects.create(federation_id='br-sec', official_name='CV Branch')

    def _match(self, home_gender='', league_gender=''):
        category = None
        league = League.objects.create(name='L', federation_id=f'l-{home_gender or "x"}-{league_gender or "x"}', season=self.season)
        if league_gender:
            category = Category.objects.create(name=f'Cat {league_gender}', gender=league_gender)
            league.categories.add(category)
        team = Team.objects.create(
            name='Local', federation_id=f't-{home_gender or "x"}-{league_gender or "x"}',
            club=self.club, category=category, gender=home_gender,
        )
        return Match.objects.create(
            league=league, home_team=team,
            match_date=timezone.now() + timedelta(days=1), venue='Pab',
        )

    def test_collects_gender_from_league_category(self):
        match = self._match(league_gender=GENDER_FEMALE)
        self.assertEqual(match_branches(match), {GENDER_FEMALE})

    def test_collects_gender_from_team(self):
        match = self._match(home_gender=GENDER_MALE)
        self.assertEqual(match_branches(match), {GENDER_MALE})

    def test_unknown_gender_returns_empty_set(self):
        match = self._match()
        self.assertEqual(match_branches(match), set())


class OrganizationBranchQTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.male_org = Organization.objects.create(slug='q-male', name='Male Org')
        cls.female_org = Organization.objects.create(
            slug='q-female', name='Female Org',
            has_male_branch=False, has_female_branch=True,
        )
        cls.none_org = Organization.objects.create(
            slug='q-none', name='None Org',
            has_male_branch=False, has_female_branch=False, has_mixed_branch=False,
        )

    def test_empty_branches_returns_none(self):
        self.assertIsNone(organization_branch_q(set()))

    def test_filters_by_active_branch(self):
        q = organization_branch_q({GENDER_FEMALE})
        result = set(Organization.objects.filter(q, slug__startswith='q-').values_list('slug', flat=True))
        self.assertEqual(result, {'q-female'})

    def test_multiple_branches_or_together(self):
        q = organization_branch_q({GENDER_MALE, GENDER_MIXED})
        result = set(Organization.objects.filter(q, slug__startswith='q-').values_list('slug', flat=True))
        self.assertEqual(result, {'q-male'})
