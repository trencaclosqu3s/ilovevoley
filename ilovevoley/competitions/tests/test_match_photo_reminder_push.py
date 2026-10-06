from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from ilovevoley.competitions.models import League, Match
from ilovevoley.competitions.tasks import send_match_photo_reminders_task
from ilovevoley.content.models import Image
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.teams.models import Club, Team

User = get_user_model()


class MatchPhotoReminderPushTest(TestCase):
    """#361: push para subir fotos 1 h después de registrarse el resultado."""

    def setUp(self):
        club = Club.objects.create(official_name='Sant Just', federation_id='SJ01')
        self.org = Organization.objects.create(name='CV Sant Just', slug='santjust', club=club)
        self.user = User.objects.create_user(username='u', email='u@test.es', password='pwd')
        self.season = Season.objects.create(name='2025-26', start_year=2025, is_current=True)
        category = Category.objects.create(name='Senior Femenino')
        league = League.objects.create(name='1a Balear', season=self.season)
        league.categories.add(category)
        self.match = Match.objects.create(
            league=league,
            home_team=Team.objects.create(name='Senior A', club=club, federation_id='T01', category=category),
            away_team=Team.objects.create(name='Rival B', federation_id='T02'),
            match_date=timezone.now() - timedelta(hours=3),
            status='finished',
            home_score=3,
            away_score=1,
            result_notified_at=timezone.now() - timedelta(minutes=70),
        )

    def run_task(self):
        with self.captureOnCommitCallbacks(execute=True):
            return send_match_photo_reminders_task()

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_sends_once_and_opens_upload_for_that_match(self, mock_push):
        self.assertEqual(self.run_task(), 1)
        _, kwargs = mock_push.call_args
        self.assertEqual(kwargs['notification_type'], 'match_photos')
        self.assertEqual(kwargs['organization_id'], self.org.id)
        self.assertTrue(kwargs['url'].endswith(f'?match={self.match.id}'))

        # Reintento de Celery: no se vuelve a enviar
        self.assertEqual(self.run_task(), 0)
        mock_push.assert_called_once()

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_waits_one_hour_after_result(self, mock_push):
        Match.objects.filter(pk=self.match.pk).update(result_notified_at=timezone.now() - timedelta(minutes=30))
        self.assertEqual(self.run_task(), 0)
        mock_push.assert_not_called()

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_catches_up_after_task_delay(self, mock_push):
        Match.objects.filter(pk=self.match.pk).update(result_notified_at=timezone.now() - timedelta(hours=5))
        self.assertEqual(self.run_task(), 1)

    @patch('ilovevoley.competitions.services.notifications.PHOTO_REMINDER_MIN_IMAGES', 1)
    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_skips_match_with_enough_photos(self, mock_push):
        Image.objects.bulk_create([Image(
            image='x.jpg', title='x', uploaded_by=self.user, organization=self.org,
            season=self.season, status='approved', match=self.match,
        )])
        self.assertEqual(self.run_task(), 0)
        mock_push.assert_not_called()

    @patch('ilovevoley.competitions.services.notifications.PHOTO_REMINDER_MIN_IMAGES', 1)
    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_rejected_photos_do_not_count(self, mock_push):
        Image.objects.bulk_create([Image(
            image='x.jpg', title='x', uploaded_by=self.user, organization=self.org,
            season=self.season, status='rejected', match=self.match,
        )])
        self.assertEqual(self.run_task(), 1)
