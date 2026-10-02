import io
from contextlib import redirect_stdout

from django.test import TestCase
from ilovevoley.core.models import Season
from ilovevoley.videos.models import League, ScrapingEndpoint


class LeagueSignalTests(TestCase):
    def setUp(self):
        self.season = Season.objects.resolve('2024-25')

    def test_create_league_creates_three_scraping_endpoints(self):
        league = League.objects.create(
            name='Liga Insular Cadete',
            federation_id='LIG-CAD-1',
            season=self.season,
        )

        endpoints = ScrapingEndpoint.objects.filter(league=league)
        self.assertEqual(endpoints.count(), 3)
        self.assertEqual(
            set(endpoints.values_list('endpoint_type', flat=True)),
            {'standings', 'results', 'calendar'},
        )

    def test_friendly_league_does_not_create_scraping_endpoints(self):
        stdout_buf = io.StringIO()
        with redirect_stdout(stdout_buf):
            league = League.objects.create(
                name='Torneo Amistoso Primavera',
                federation_id='FRIENDLY-1',
                season=self.season,
                competition_type='friendly',
            )

        self.assertEqual(ScrapingEndpoint.objects.filter(league=league).count(), 0)
        self.assertEqual(stdout_buf.getvalue(), '')
