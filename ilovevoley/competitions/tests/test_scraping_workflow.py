"""Reparto del scraping por liga (#601): sin sleep en el worker y con resumen agregado."""
from unittest import mock

from django.test import TestCase, override_settings

from ilovevoley.competitions.models import League
from ilovevoley.competitions.tasks_scraping import (
    build_scrape_all_leagues_workflow,
    scrape_clubs_summary_task,
    scrape_clubs_task,
    scrape_endpoint_summary_task,
    scrape_leagues_summary_task,
    scrape_results_task,
)
from ilovevoley.competitions.tasks_enrichment import enrich_leagues_summary_task, enrich_matches_json_task
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


class EnrichLeaguesWorkflowTest(TestCase):
    def setUp(self):
        season = Season.objects.current()
        for n in range(2):
            League.objects.create(name=f'Liga {n}', federation_id=str(n), season=season, is_active=True)

    def test_enrich_all_spaces_leagues_by_countdown(self):
        with mock.patch('ilovevoley.competitions.tasks_enrichment.chord') as chord_mock:
            result = enrich_matches_json_task.run(delay=1.5)
        header = chord_mock.call_args.args[0]
        self.assertEqual(result, {'status': 'queued', 'leagues_queued': 2})
        self.assertEqual([sig.options['countdown'] for sig in header], [0.0, 1.5])

    def test_summary_counts_failed_leagues(self):
        stats = [
            {'league': 'A', 'success': True, 'enriched': 3, 'new': 1, 'errors': []},
            {'league': 'B', 'success': False, 'enriched': 0, 'new': 0, 'errors': [{'league': 'B', 'error': 'x'}]},
        ]
        total = enrich_leagues_summary_task.run(stats, notify=False)
        self.assertEqual((total['total_enriched'], total['total_new'], total['leagues_errors']), (3, 1, 1))


class ScrapeResultsWorkflowTest(TestCase):
    def setUp(self):
        season = Season.objects.current()
        for n in range(2):
            League.objects.create(name=f'Liga {n}', federation_id=str(n), season=season, is_active=True)

    def test_results_fan_out_passes_round_and_delay_per_league(self):
        with mock.patch('ilovevoley.competitions.tasks_scraping.chord') as chord_mock:
            result = scrape_results_task.run(round_number=4, delay=3.0)
        header = chord_mock.call_args.args[0]
        self.assertEqual(result, {'status': 'queued', 'leagues_queued': 2})
        self.assertEqual([sig.options['countdown'] for sig in header], [0.0, 3.0])
        self.assertTrue(all(sig.args[1:] == (4, 3.0) for sig in header))

    def test_unknown_league_id_is_an_error_not_a_fan_out(self):
        result = scrape_results_task.run(league_id='nope')
        self.assertEqual(result['status'], 'error')

    @override_settings(NOTIFICATION_EMAIL_ENABLED=True)
    def test_summary_subject_names_the_kind(self):
        stats = [{'league': 'B', 'success': False, 'matches': 0, 'rounds': 0,
                  'errors': [{'league': 'B', 'error': 'x'}]}]
        with mock.patch('ilovevoley.competitions.tasks_scraping.mail_admins') as mail:
            scrape_endpoint_summary_task.run(stats, 'calendario')
        self.assertIn('calendario', mail.call_args.args[0])


class ScrapeClubsWorkflowTest(TestCase):
    def test_clubs_fan_out_spaces_each_club_by_countdown(self):
        listing = mock.Mock(**{'json.return_value': {'items': [{'ID': 1, 'Nombre': 'A'}, {'ID': 2, 'Nombre': 'B'}]}})
        with mock.patch('requests.get', return_value=listing), \
                mock.patch('ilovevoley.competitions.tasks_scraping.chord') as chord_mock:
            result = scrape_clubs_task.run(delay=2.0)
        header = chord_mock.call_args.args[0]
        self.assertEqual(result, {'status': 'queued', 'clubs_queued': 2})
        self.assertEqual([(sig.args, sig.options['countdown']) for sig in header], [((1, 'A'), 0.0), ((2, 'B'), 2.0)])

    def test_summary_counts_created_updated_and_errors(self):
        results = [
            {'created': True, 'error': None},
            {'created': False, 'error': None},
            {'created': None, 'error': 'fallo'},
        ]
        total = scrape_clubs_summary_task.run(results, match_teams=False)
        self.assertEqual((total['clubs_created'], total['clubs_updated'], total['errors']), (1, 1, ['fallo']))
