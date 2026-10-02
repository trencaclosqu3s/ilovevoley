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


class CleanVenueMapsUrlsMigrationTest(TransactionTestCase):
    """La migración 0020 limpia URLs erróneas/404 y completa coordenadas de las 8 sedes restantes."""

    migrate_from = ('competitions', '0019_federationcallup_callup_type')
    migrate_to = ('competitions', '0020_clean_venue_maps_urls_and_add_coordinates')

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_from])
        old_apps = self.executor.loader.project_state([self.migrate_from]).apps
        Venue = old_apps.get_model('competitions', 'Venue')

        # Sede con URL cruzada de la precarga 0013
        Venue.objects.create(
            name='Pavelló Andreu Trobat',
            city='Algaida',
            google_maps_url='https://maps.app.goo.gl/wTQiRiLduquRbF9s7',
        )
        # Sede con URL sintética 404 y sin coordenadas
        Venue.objects.create(
            name='Pavelló Joan Seguí',
            city='Palma',
            google_maps_url='https://maps.app.goo.gl/9ZpZgZgZgZgZgZgZ8',
            latitude=None,
            longitude=None,
        )
        # Sede con URL personalizada legítima (no debe borrarse)
        Venue.objects.create(
            name='Pavelló Personalitzat',
            city='Palma',
            google_maps_url='https://maps.google.com/?q=custom_valid_link',
        )

    def tearDown(self):
        self.executor.loader.build_graph()
        self.executor.migrate(self.executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_migration_cleans_seed_urls_and_sets_missing_coordinates(self):
        self.executor.loader.build_graph()
        self.executor.migrate([self.migrate_to])
        new_apps = self.executor.loader.project_state([self.migrate_to]).apps
        Venue = new_apps.get_model('competitions', 'Venue')

        algaida = Venue.objects.get(name='Pavelló Andreu Trobat')
        self.assertEqual(algaida.google_maps_url, '')

        joan_segui = Venue.objects.get(name='Pavelló Joan Seguí')
        self.assertEqual(joan_segui.google_maps_url, '')
        self.assertIsNotNone(joan_segui.latitude)
        self.assertIsNotNone(joan_segui.longitude)
        self.assertEqual(str(joan_segui.latitude), '39.586942')
        self.assertEqual(str(joan_segui.longitude), '2.620204')

        custom = Venue.objects.get(name='Pavelló Personalitzat')
        self.assertEqual(custom.google_maps_url, 'https://maps.google.com/?q=custom_valid_link')
