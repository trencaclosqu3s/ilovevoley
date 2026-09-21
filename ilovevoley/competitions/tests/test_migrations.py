from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class LeagueSeasonBackfillMigrationTest(TransactionTestCase):
    """La conversión League.season (string) -> FK no debe perder temporadas."""

    migrate_from = ('competitions', '0004_remove_league_category')
    migrate_to = ('competitions', '0005_alter_league_unique_together_alter_league_season')

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_from])
        old_apps = self.executor.loader.project_state([self.migrate_from]).apps
        League = old_apps.get_model('competitions', 'League')
        League.objects.create(name='Liga Antigua', federation_id='OLD-1', season='2024-2025')
        League.objects.create(name='Liga Compartida', federation_id='OLD-3', season='2024-25')
        League.objects.create(name='Liga Basura', federation_id='OLD-2', season='temp')

    def tearDown(self):
        self.executor.loader.build_graph()
        self.executor.migrate(self.executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_backfill_normaliza_y_conserva_temporadas(self):
        self.executor.loader.build_graph()
        self.executor.migrate([self.migrate_to])
        new_apps = self.executor.loader.project_state([self.migrate_to]).apps
        League = new_apps.get_model('competitions', 'League')
        Season = new_apps.get_model('core', 'Season')

        antigua = League.objects.get(federation_id='OLD-1')
        compartida = League.objects.get(federation_id='OLD-3')
        basura = League.objects.get(federation_id='OLD-2')

        self.assertEqual(antigua.season.name, '2024-25')
        # '2024-2025' y '2024-25' deben reutilizar la misma Season, no duplicarla.
        self.assertEqual(compartida.season_id, antigua.season_id)
        self.assertEqual(Season.objects.filter(name='2024-25').count(), 1)
        # Un string no reconocido queda sin temporada, no rompe la migración.
        self.assertIsNone(basura.season_id)
