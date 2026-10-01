"""Topología de Celery: colas separadas, timeouts y bases Redis distintas.

El objetivo de negocio es que un scraping federativo colgado no bloquee el
envío de emails ni la generación de media. Eso depende de que cada tarea caiga
en la cola correcta y de que los workers las consuman por separado, así que
este test fija el routing tarea -> cola.
"""
from django.conf import settings
from django.test import SimpleTestCase

from config.celery import app


QUEUE_BY_TASK = {
    # default: emails y notificaciones
    'notify_image_pending': 'default',
    'notify_images_pending_batch': 'default',
    'notify_new_user_pending': 'default',
    'notify_membership_pending': 'default',
    'notify_user_moderation_result': 'default',
    'notify_image_moderation_result': 'default',
    'send_admin_email_to_users': 'default',
    'send_404_immediate_alert': 'default',
    # media: Vision, miniaturas y compresión de ZIP de álbumes
    'analyze_image_with_vision': 'media',
    'generate_image_thumbnails_task': 'media',
    'build_album_zip': 'media',
    # scraping: scrapers federativos y enriquecimiento
    'scrape_all_leagues': 'scraping',
    'scrape_league': 'scraping',
    'scrape_calendar': 'scraping',
    'scrape_results': 'scraping',
    'scrape_clubs': 'scraping',
    'scrape_teams': 'scraping',
    'handle_withdrawn_teams': 'scraping',
    'scrape_and_enrich_all': 'scraping',
    'scrape_json_results': 'scraping',
    'scrape_json_upcoming': 'scraping',
    'process_json_unified': 'scraping',
    'enrich_matches_json': 'scraping',
    'enrich_single_league_json': 'scraping',
    'enrich_upcoming_matches': 'scraping',
    'scrape_rfevb_competition': 'scraping',
    'scrape_rfevb_final_classification': 'scraping',
}


class CeleryQueueRoutingTest(SimpleTestCase):
    def test_every_task_routes_to_its_queue(self):
        for task_name, expected_queue in QUEUE_BY_TASK.items():
            route = app.amqp.router.route({}, task_name) or {}
            queue = route.get('queue')
            queue_name = getattr(queue, 'name', queue)
            self.assertEqual(
                queue_name,
                expected_queue,
                msg=f'{task_name} debería enrutarse a la cola {expected_queue}',
            )

    def test_time_limits_are_configured(self):
        self.assertEqual(settings.CELERY_TASK_SOFT_TIME_LIMIT, 600)
        self.assertEqual(settings.CELERY_TASK_TIME_LIMIT, 900)

    def test_late_ack_and_prefetch_one(self):
        self.assertTrue(settings.CELERY_TASK_ACKS_LATE)
        self.assertEqual(settings.CELERY_WORKER_PREFETCH_MULTIPLIER, 1)

    def test_redis_logical_databases_are_separated(self):
        self.assertTrue(settings.CELERY_BROKER_URL.endswith('/0'))
        self.assertTrue(settings.CELERY_RESULT_BACKEND.endswith('/1'))
        self.assertTrue(settings.REDIS_CACHE_URL.endswith('/2'))


class BeatScheduleTest(SimpleTestCase):
    EXPECTED_TASKS = {
        'cleanup-expired-album-zips': 'cleanup_expired_album_zips',
        'send-match-reminders-2h': 'send_match_reminders_2h',
        'scrape-clubs': 'scrape_clubs',
        'enrich-matches': 'enrich_matches_json',
        'scrape-all-leagues': 'scrape_all_leagues',
        'scrape-json-results': 'scrape_json_results',
        'scrape-json-upcoming': 'scrape_json_upcoming',
        'scrape-and-enrich-all': 'scrape_and_enrich_all',
        'scrape-balearic-callups': 'scrape_balearic_callups',
        'scrape-balearic-tracking': 'scrape_balearic_tracking',
    }

    LEGACY_MANUAL_NAMES = {
        'clubs',
        'enrich_matches',
        'json results',
        'scrape ligas',
        "scrape y enrich to'",
        'upcoming_matches',
    }

    def test_schedule_entries_match_expected_tasks(self):
        actual = {name: entry['task'] for name, entry in settings.CELERY_BEAT_SCHEDULE.items()}
        self.assertEqual(actual, self.EXPECTED_TASKS)

    def test_scheduled_tasks_are_registered(self):
        app.loader.import_default_modules()
        for name, entry in settings.CELERY_BEAT_SCHEDULE.items():
            self.assertIn(
                entry['task'],
                app.tasks,
                msg=f'{name} apunta a una tarea no registrada: {entry["task"]}',
            )

    def test_no_legacy_manual_names_remain(self):
        overlap = self.LEGACY_MANUAL_NAMES & set(settings.CELERY_BEAT_SCHEDULE)
        self.assertFalse(overlap, msg=f'Nombres legacy aún en el schedule: {overlap}')

    def test_beat_timezone_is_madrid(self):
        self.assertEqual(settings.CELERY_TIMEZONE, 'Europe/Madrid')
