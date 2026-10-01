from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from ilovevoley.competitions.models import League, Match
from ilovevoley.competitions.services.delta_detector import detect_and_record_match_changes
from ilovevoley.competitions.services.notifications import notify_match_result
from ilovevoley.core.models import Category, GENDER_FEMALE, Organization, Season
from ilovevoley.teams.models import Club, Team


class MatchBranchPushTest(TestCase):
    def setUp(self):
        self.club = Club.objects.create(official_name='Sant Just', federation_id='BRP01')
        self.org = Organization.objects.create(
            name='CV Sant Just', slug='santjust-branch', club=self.club, notify_match_changes=True,
        )
        self.season = Season.objects.create(name='2025-26', start_year=2025, is_current=True)
        self.female_category = Category.objects.create(name='Senior Femenino Push', gender=GENDER_FEMALE)
        self.team1 = Team.objects.create(
            name='Senior A F', club=self.club, federation_id='BRP-T1', category=self.female_category,
        )
        self.team2 = Team.objects.create(name='Rival B F', federation_id='BRP-T2')
        self.league = League.objects.create(name='1a Balear F', federation_id='BRP-L', season=self.season)
        self.league.categories.add(self.female_category)
        self.match_date = timezone.now() + timedelta(days=3)
        self.match = Match.objects.create(
            league=self.league, home_team=self.team1, away_team=self.team2,
            match_date=self.match_date, venue='Pab', status='scheduled',
        )

    @override_settings(MATCH_CHANGE_PUSH_ENABLED=True)
    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_female_change_push_skipped_when_branch_off(self, mock_push):
        new_date = self.match_date + timedelta(hours=2)
        with self.captureOnCommitCallbacks(execute=True):
            detect_and_record_match_changes(self.match, {'match_date': new_date})
        mock_push.assert_not_called()

    @override_settings(MATCH_CHANGE_PUSH_ENABLED=True)
    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_female_change_push_sent_when_branch_on(self, mock_push):
        self.org.has_female_branch = True
        self.org.save(update_fields=['has_female_branch'])
        new_date = self.match_date + timedelta(hours=2)
        with self.captureOnCommitCallbacks(execute=True):
            detect_and_record_match_changes(self.match, {'match_date': new_date})
        mock_push.assert_called_once()

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_result_push_respects_branch(self, mock_push):
        self.match.status = 'finished'
        self.match.home_score = 3
        self.match.away_score = 1
        self.match.save(update_fields=['status', 'home_score', 'away_score'])
        with self.captureOnCommitCallbacks(execute=True):
            notify_match_result(self.match)
        mock_push.assert_not_called()

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_result_push_sent_when_branch_on(self, mock_push):
        self.org.has_female_branch = True
        self.org.save(update_fields=['has_female_branch'])
        self.match.status = 'finished'
        self.match.home_score = 3
        self.match.away_score = 1
        self.match.save(update_fields=['status', 'home_score', 'away_score'])
        with self.captureOnCommitCallbacks(execute=True):
            notify_match_result(self.match)
        mock_push.assert_called_once()

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_result_push_tenant_respects_branch(self, mock_push):
        self.match.status = 'finished'
        self.match.home_score = 3
        self.match.away_score = 1
        self.match.save(update_fields=['status', 'home_score', 'away_score'])
        with self.captureOnCommitCallbacks(execute=True):
            notify_match_result(self.match, tenant=self.org)
        mock_push.assert_not_called()

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_result_push_tenant_sent_when_branch_on(self, mock_push):
        self.org.has_female_branch = True
        self.org.save(update_fields=['has_female_branch'])
        self.match.status = 'finished'
        self.match.home_score = 3
        self.match.away_score = 1
        self.match.save(update_fields=['status', 'home_score', 'away_score'])
        with self.captureOnCommitCallbacks(execute=True):
            notify_match_result(self.match, tenant=self.org)
        mock_push.assert_called_once()

    @override_settings(MATCH_CHANGE_PUSH_ENABLED=True)
    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_unknown_gender_still_sent(self, mock_push):
        self.org.has_male_branch = False
        self.org.save(update_fields=['has_male_branch'])
        neutral_league = League.objects.create(name='Liga neutra', federation_id='BRP-L2', season=self.season)
        neutral_team = Team.objects.create(name='Neutro', club=self.club, federation_id='BRP-T3')
        neutral_match = Match.objects.create(
            league=neutral_league, home_team=neutral_team,
            match_date=timezone.now() + timedelta(days=3), venue='Pab', status='scheduled',
        )
        with self.captureOnCommitCallbacks(execute=True):
            detect_and_record_match_changes(neutral_match, {'venue': 'Nueva pista'})
        mock_push.assert_called_once()
