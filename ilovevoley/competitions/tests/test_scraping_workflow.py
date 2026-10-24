"""Reparto del scraping por liga (#601): sin sleep en el worker y con resumen agregado."""
from unittest import mock

from django.test import TestCase, override_settings

from ilovevoley.competitions.models import League
from ilovevoley.competitions.tasks_scraping import (
    build_scrape_all_leagues_workflow,
    scrape_leagues_summary_task,
)
from ilovevoley.core.models import Season


class ScrapeAllLeaguesWorkflowTest(TestCase):
    def setUp(self):
        season = Season.objects.current()
        for n in range(3):
            League.objects.create(name=f'Liga {n}', federation_id=str(n), season=season, is_active=True)

    def test_leagues_are_spaced_by_countdown_not_sleep(self):
        """Regresión del bloqueo: entre ligas el worker no duerme, se escalona el arranque."""
        with mock.patch('ilovevoley.competitions.tasks_scraping.chord') as chord_mock:
            workflow, queued = build_scrape_all_leagues_workflow(delay=2.0)
        header = chord_mock.call_args.args[0]
        self.assertEqual(queued, 3)
        self.assertEqual([sig.options['countdown'] for sig in header], [0.0, 2.0, 4.0])

    def test_no_active_leagues_builds_nothing(self):
        League.objects.update(is_active=False)
        self.assertEqual(build_scrape_all_leagues_workflow(), (None, 0))

    @override_settings(NOTIFICATION_EMAIL_ENABLED=True)
    def test_summary_aggregates_and_mails_admins_on_errors(self):
        stats = [
            {'league': 'A', 'success': True, 'teams': 2, 'matches': 5, 'standings': 1, 'errors': []},
            {'league': 'B', 'success': False, 'teams': 0, 'matches': 0, 'standings': 0,
             'errors': [{'league': 'B', 'endpoint': 'general', 'error': 'boom'}]},
        ]
        with mock.patch('ilovevoley.competitions.tasks_scraping.mail_admins') as mail:
            total = scrape_leagues_summary_task.run(stats)
        self.assertEqual(
            (total['leagues_processed'], total['leagues_success'], total['leagues_errors']), (2, 1, 1)
        )
        self.assertEqual((total['total_teams'], total['total_matches']), (2, 5))
        mail.assert_called_once()
