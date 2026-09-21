from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

from ilovevoley.core.models import season_start_year_for_date


class RosterSeasonBackfillMigrationTest(TransactionTestCase):
    """Los roles existentes se reasignan a la temporada pasada, con nombre canónico."""

    migrate_from = ('rosters', '0004_delete_legacy_player_staff')
    migrate_to = ('rosters', '0005_remove_playerrole_unique_active_player_role_and_more')

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_from])
        self.executor.loader.build_graph()
        old_apps = self.executor.loader.project_state([self.migrate_from]).apps
        leaf_apps = self.executor.loader.project_state(self.executor.loader.graph.leaf_nodes()).apps

        Team = leaf_apps.get_model('teams', 'Team')
        team = Team.objects.create(name='Equipo RS', federation_id='T-RS')
        Person = old_apps.get_model('rosters', 'Person')
        PlayerRole = old_apps.get_model('rosters', 'PlayerRole')
        StaffRole = old_apps.get_model('rosters', 'StaffRole')
        person = Person.objects.create(first_name='Ana', last_name='Backfill')
        PlayerRole.objects.create(person_id=person.id, team_id=team.id, jersey_number=5)
        StaffRole.objects.create(person_id=person.id, team_id=team.id, role='head_coach')

    def tearDown(self):
        self.executor.loader.build_graph()
        self.executor.migrate(self.executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_backfill_temporada_pasada(self):
        self.executor.loader.build_graph()
        self.executor.migrate([self.migrate_to])
        new_apps = self.executor.loader.project_state([self.migrate_to]).apps
        PlayerRole = new_apps.get_model('rosters', 'PlayerRole')
        StaffRole = new_apps.get_model('rosters', 'StaffRole')
        Season = new_apps.get_model('core', 'Season')

        start_year = season_start_year_for_date(timezone.now()) - 1
        expected = f'{start_year}-{(start_year + 1) % 100:02d}'

        role = PlayerRole.objects.get()
        staff = StaffRole.objects.get()
        self.assertEqual(role.season.name, expected)
        self.assertEqual(staff.season_id, role.season_id)
        self.assertEqual(Season.objects.filter(name=expected).count(), 1)
