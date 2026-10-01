from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class CategoryGenderBackfillMigrationTest(TransactionTestCase):
    """La migración de datos rellena Category.gender parseando el nombre."""

    migrate_from = ('core', '0009_organization_notify_match_changes')

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_from])
        self.executor.loader.build_graph()
        old_apps = self.executor.loader.project_state([self.migrate_from]).apps
        Category = old_apps.get_model('core', 'Category')
        Category.objects.create(name='Senior Femenino')
        Category.objects.create(name='Infantil Masculino')
        Category.objects.create(name='Senior')

    def tearDown(self):
        self.executor.loader.build_graph()
        self.executor.migrate(self.executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_backfill_sets_gender_from_name(self):
        self.executor.loader.build_graph()
        leaf = self.executor.loader.graph.leaf_nodes('core')
        self.executor.migrate(leaf)
        apps = self.executor.loader.project_state(leaf).apps
        Category = apps.get_model('core', 'Category')

        self.assertEqual(Category.objects.get(name='Senior Femenino').gender, 'female')
        self.assertEqual(Category.objects.get(name='Infantil Masculino').gender, 'male')
        self.assertEqual(Category.objects.get(name='Senior').gender, '')
