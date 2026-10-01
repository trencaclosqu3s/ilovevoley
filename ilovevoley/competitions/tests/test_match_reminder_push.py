from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from ilovevoley.competitions.models import League, Match
from ilovevoley.competitions.services.delta_detector import detect_and_record_match_changes
from ilovevoley.competitions.services.notifications import notify_match_reminder
from ilovevoley.competitions.tasks import send_match_reminders_2h_task
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.teams.models import Club, Team

User = get_user_model()


class MatchReminderPushTest(TestCase):
    def setUp(self):
        self.club = Club.objects.create(official_name='Sant Just', federation_id='SJ01')
        self.org = Organization.objects.create(
            name='CV Sant Just', slug='santjust', club=self.club
        )
        self.user = User.objects.create_superuser(username='admin', email='a@test.es', password='pwd')
        self.season = Season.objects.create(name='2025-26', start_year=2025, is_current=True)
        self.category = Category.objects.create(name='Senior Femenino')
        self.team1 = Team.objects.create(
            name='Senior A', club=self.club, federation_id='T01', category=self.category
        )
        self.team2 = Team.objects.create(name='Rival B', federation_id='T02')
        self.league = League.objects.create(name='1a Balear', season=self.season)
        self.league.categories.add(self.category)

        # Match in exactly 2 hours (120 minutes)
        self.match_date_2h = timezone.now() + timedelta(hours=2)
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team1,
            away_team=self.team2,
            match_date=self.match_date_2h,
            status='scheduled',
        )

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_reminder_push_sent_for_scheduled_match(self, mock_push):
        """Un partido a 2 h envía push con tipo match_reminder, categorías y marca reminder_sent_at."""
        with self.captureOnCommitCallbacks(execute=True):
            sent = send_match_reminders_2h_task()

        self.assertEqual(sent, 1)
        mock_push.assert_called_once()
        _, kwargs = mock_push.call_args
        self.assertEqual(kwargs['organization_id'], self.org.id)
        self.assertEqual(kwargs['notification_type'], 'match_reminder')
        self.assertIn('Recordatorio de partido: Senior A vs Rival B', kwargs['title'])
        self.assertIn('2 h', kwargs['body'])
        self.assertIn('rodilleras', kwargs['body'].lower())
        self.assertIn(self.category.id, kwargs['category_ids'])
        self.assertIn(f"/competitions/partidos/{self.match.id}/", kwargs['url'])

        self.match.refresh_from_db()
        self.assertIsNotNone(self.match.reminder_sent_at)

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_idempotency_task_runs_twice_notifies_once(self, mock_push):
        """La tarea de Celery puede ejecutarse múltiples veces pero solo notifica una vez."""
        with self.captureOnCommitCallbacks(execute=True):
            sent_first = send_match_reminders_2h_task()

        self.assertEqual(sent_first, 1)
        self.assertEqual(mock_push.call_count, 1)

        # Segunda ejecución inmediata
        with self.captureOnCommitCallbacks(execute=True):
            sent_second = send_match_reminders_2h_task()

        self.assertEqual(sent_second, 0)
        self.assertEqual(mock_push.call_count, 1)

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_matches_outside_window_are_ignored(self, mock_push):
        """Partidos fuera de la ventana de ~2 horas (p. ej. a 5 h o a 30 min) no se notifican."""
        Match.objects.all().delete()

        # Partido a 5 horas
        match_5h = Match.objects.create(
            league=self.league,
            home_team=self.team1,
            away_team=self.team2,
            match_date=timezone.now() + timedelta(hours=5),
            status='scheduled',
        )
        # Partido a 30 minutos
        match_30m = Match.objects.create(
            league=self.league,
            home_team=self.team1,
            away_team=self.team2,
            match_date=timezone.now() + timedelta(minutes=30),
            status='scheduled',
        )

        with self.captureOnCommitCallbacks(execute=True):
            sent = send_match_reminders_2h_task()

        self.assertEqual(sent, 0)
        mock_push.assert_not_called()
        match_5h.refresh_from_db()
        match_30m.refresh_from_db()
        self.assertIsNone(match_5h.reminder_sent_at)
        self.assertIsNone(match_30m.reminder_sent_at)

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_excluded_statuses_do_not_send_reminder(self, mock_push):
        """Partidos finalizados, aplazados, cancelados o retirados no reciben recordatorio."""
        for invalid_status in ['finished', 'postponed', 'cancelled']:
            self.match.status = invalid_status
            self.match.save(update_fields=['status'])

            with self.captureOnCommitCallbacks(execute=True):
                sent = send_match_reminders_2h_task()

            self.assertEqual(sent, 0)
            mock_push.assert_not_called()

        # Caso withdrawn
        self.match.status = 'withdrawn'
        self.match.save(update_fields=['status'])
        with self.captureOnCommitCallbacks(execute=True):
            sent = send_match_reminders_2h_task()
        self.assertEqual(sent, 0)
        mock_push.assert_not_called()

    @patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay')
    def test_rescheduled_match_resets_reminder_sent_at(self, mock_push):
        """Si un partido cambia de fecha/hora, reminder_sent_at se resetea para poder avisar de nuevo."""
        # 1. Enviar primer recordatorio
        with self.captureOnCommitCallbacks(execute=True):
            send_match_reminders_2h_task()

        self.match.refresh_from_db()
        self.assertIsNotNone(self.match.reminder_sent_at)

        # 2. El partido se reprograma a dentro de 4 horas
        new_date = timezone.now() + timedelta(hours=4)
        detect_and_record_match_changes(self.match, {'match_date': new_date}, save_changes=True)

        self.match.refresh_from_db()
        self.assertIsNone(self.match.reminder_sent_at)

    def test_celery_task_name_and_beat_schedule(self):
        """La tarea Celery tiene name explícito y está registrada en CELERY_BEAT_SCHEDULE."""
        self.assertEqual(send_match_reminders_2h_task.name, 'send_match_reminders_2h')
        self.assertIn('send-match-reminders-2h', settings.CELERY_BEAT_SCHEDULE)
        beat_entry = settings.CELERY_BEAT_SCHEDULE['send-match-reminders-2h']
        self.assertEqual(beat_entry['task'], 'send_match_reminders_2h')

    @patch('ilovevoley.users.tasks.send_web_push', return_value=True)
    def test_reminder_respects_user_notification_preference(self, mock_webpush):
        """Usuarios que desactivaron match_reminder no reciben push; otros sí."""
        from ilovevoley.users.models import NotificationPreference, NotificationType, WebPushSubscription
        from ilovevoley.users.tasks import notify_web_push_organization_task

        # Usuario 1: desactiva match_reminder
        u_disabled = User.objects.create_user(username='u_disabled', email='dis@test.es')
        WebPushSubscription.objects.create(
            user=u_disabled, organization=self.org, endpoint='https://fcm.test/disabled', p256dh='k1', auth='a1'
        )
        NotificationPreference.objects.create(
            user=u_disabled, organization=self.org, notification_type=NotificationType.MATCH_REMINDER, is_enabled=False
        )

        # Usuario 2: sin preferencia (activo por defecto)
        u_active = User.objects.create_user(username='u_active', email='act@test.es')
        WebPushSubscription.objects.create(
            user=u_active, organization=self.org, endpoint='https://fcm.test/active', p256dh='k2', auth='a2'
        )

        # Ejecutamos la tarea capturando el dispatch real a notify_web_push_organization_task
        with patch('ilovevoley.users.tasks.notify_web_push_organization_task.delay', side_effect=notify_web_push_organization_task) as mock_delay:
            with self.captureOnCommitCallbacks(execute=True):
                send_match_reminders_2h_task()

        # Solo debe recibirlo u_active (1 llamada a send_web_push)
        self.assertEqual(mock_webpush.call_count, 1)
        sub_called = mock_webpush.call_args[0][0]
        self.assertEqual(sub_called.user_id, u_active.id)

