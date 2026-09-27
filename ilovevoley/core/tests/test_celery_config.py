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
