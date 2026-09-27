"""Contract tests for Sentry SDK initialization (issue #133).

Periodic-task monitoring (Sentry Crons) and profiling are wired through
``config.sentry.configure``. A silent regression in those options would disable
observability in production without any visible error, so the contract is
pinned here.
"""
from unittest.mock import patch

from django.test import SimpleTestCase

from config import sentry

DSN = 'https://key@example.ingest.sentry.io/1'


class SentryConfigureTest(SimpleTestCase):
    def test_init_enables_beat_monitoring_and_profiling(self):
        with patch('sentry_sdk.init') as mock_init:
            sentry.configure(
                dsn=DSN,
                debug=False,
                traces_sample_rate=0.1,
                profiles_sample_rate=0.1,
                monitor_beat_tasks=True,
            )

        options = mock_init.call_args.kwargs
        self.assertEqual(options['traces_sample_rate'], 0.1)
        self.assertEqual(options['profiles_sample_rate'], 0.1)
        integrations = {type(i).__name__: i for i in options['integrations']}
        self.assertTrue(integrations['CeleryIntegration'].monitor_beat_tasks)

    def test_no_init_in_debug(self):
        with patch('sentry_sdk.init') as mock_init:
            sentry.configure(dsn=DSN, debug=True, traces_sample_rate=0.1)

        mock_init.assert_not_called()

    def test_no_init_without_dsn(self):
        with patch('sentry_sdk.init') as mock_init:
            sentry.configure(dsn='', debug=False, traces_sample_rate=0.1)

        mock_init.assert_not_called()
