import json
from unittest.mock import patch
from django.test import Client, TestCase, override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from ilovevoley.core.models import Organization, Season
from ilovevoley.competitions.models import League, Match
from ilovevoley.teams.models import Club, Team

User = get_user_model()


@override_settings(ALLOWED_HOSTS=['santjust.ilovevoley.es', 'localhost', 'testserver'])
class MatchPushTriggerTest(TestCase):
    def setUp(self):
        self.club = Club.objects.create(official_name='Sant Just', federation_id='SJ01')
        self.org = Organization.objects.create(name='CV Sant Just', slug='santjust', club=self.club)
        self.user = User.objects.create_superuser(username='admin', email='a@test.es', password='pwd')
        self.season = Season.objects.create(name='2025-26', start_year=2025, is_current=True)
        self.team1 = Team.objects.create(name='Senior A', club=self.club, federation_id='T01')
        self.team2 = Team.objects.create(name='Rival B', federation_id='T02')
        self.league = League.objects.create(name='1a Balear', season=self.season)
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team1,
            away_team=self.team2,
            match_date=timezone.now(),
        )
        self.client = Client()
        self.client.login(username='admin', password='pwd')

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_saving_score_triggers_webpush(self, mock_push_task):
        url = f'/competitions/ajax/partidos/{self.match.id}/resultado/'
        payload = {'home_score': 3, 'away_score': 1}
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                url,
                data=json.dumps(payload),
                content_type='application/json',
                HTTP_HOST='santjust.ilovevoley.es',
            )
        self.assertEqual(response.status_code, 200)
        mock_push_task.assert_called_once()
        _, kwargs = mock_push_task.call_args
        self.assertIn('3 - 1', kwargs.get('body', ''))
        self.assertEqual(kwargs.get('notification_type'), 'match_result')

