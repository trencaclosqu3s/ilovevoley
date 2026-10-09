"""Topología de Celery: colas separadas, timeouts y bases Redis distintas.

El objetivo de negocio es que un scraping federativo colgado no bloquee el
envío de emails ni la generación de media. Eso depende de que cada tarea caiga
en la cola correcta y de que los workers las consuman por separado, así que
este test fija el routing tarea -> cola.
"""
import inspect

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
    'send_match_reminders_2h': 'default',
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
    'scrape_balearic_callups': 'scraping',
    'scrape_balearic_tracking': 'scraping',
    'scrape_match_actas': 'scraping',
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


class BeatScheduleTest(SimpleTestCase):
    def setUp(self):
        # autodiscover_tasks es perezoso: hay que forzar la carga para que las
        # tareas de cada app estén en el registro.
        app.loader.import_default_modules()

    def test_scheduled_tasks_exist_and_accept_their_args(self):
        """Un nombre de tarea o de argumento mal escrito solo se ve en runtime en
        el worker; aquí se valida contra la firma registrada. ``bind`` exige
        además los argumentos obligatorios que la tarea no pueda suplir."""
        self.assertTrue(settings.CELERY_BEAT_SCHEDULE, 'el schedule no puede quedar vacío')
        for name, entry in settings.CELERY_BEAT_SCHEDULE.items():
            task_name = entry['task']
            self.assertIn(task_name, app.tasks, msg=f'{name} apunta a una tarea no registrada: {task_name}')
            inspect.signature(app.tasks[task_name].run).bind(
                *entry.get('args', ()), **entry.get('kwargs', {})
            )

    def test_beat_timezone_matches_django_timezone(self):
        """Los crontab se interpretan en CELERY_TIMEZONE; si deja de coincidir con
        TIME_ZONE, las horas del schedule se desplazan en silencio."""
        self.assertEqual(settings.CELERY_TIMEZONE, settings.TIME_ZONE)
