from datetime import timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class RoleIdentityMigrationTest(TransactionTestCase):
    """La plantilla repartida entre fases se unifica por identidad (#447).

    Caso real de producción: la misma plantilla dada de alta en dos fases del
    mismo equipo, con una jugadora que cambió de posición entre ellas.
    """

    migrate_from = ('rosters', '0011_role_identity')

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_from])
        self.executor.loader.build_graph()
        apps = self.executor.loader.project_state([self.migrate_from]).apps
        TeamIdentity = apps.get_model('teams', 'TeamIdentity')
        Team = apps.get_model('teams', 'Team')
        Season = apps.get_model('core', 'Season')
        Person = apps.get_model('rosters', 'Person')
        PlayerRole = apps.get_model('rosters', 'PlayerRole')
        StaffRole = apps.get_model('rosters', 'StaffRole')

        identity = TeamIdentity.objects.create(core_name='CV GROC', core_name_normalized='cv groc')
        league_phase = Team.objects.create(federation_id='10', name='CV GROC', identity=identity)
        cup_phase = Team.objects.create(federation_id='48', name='CV GROC', identity=identity, is_active=False)
        season = Season.objects.create(name='2025-26', start_year=2025, end_year=2026)
        player = Person.objects.create(first_name='Ana', last_name='Pons', birth_year=2012)
        coach = Person.objects.create(first_name='Joan', last_name='Mas', birth_year=1980)

        old = PlayerRole.objects.create(person=player, team=cup_phase, season=season, jersey_number=13, position='middle_blocker')
        new = PlayerRole.objects.create(person=player, team=league_phase, season=season, jersey_number=13, position='setter')
        PlayerRole.objects.filter(pk=old.pk).update(updated_at=timezone.now() - timedelta(days=200))
        PlayerRole.objects.filter(pk=new.pk).update(updated_at=timezone.now())
        StaffRole.objects.create(person=coach, team=cup_phase, season=season, role='head_coach')
        StaffRole.objects.create(person=coach, team=league_phase, season=season, role='head_coach')
        StaffRole.objects.create(person=coach, team=league_phase, season=season, role='delegate')
        self.identity_id = identity.pk

    def tearDown(self):
        self.executor.loader.build_graph()
        self.executor.migrate(self.executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_duplicates_collapse_into_last_state_per_identity(self):
        self.executor.loader.build_graph()
        leaf = self.executor.loader.graph.leaf_nodes('rosters')
        self.executor.migrate(leaf)
        apps = self.executor.loader.project_state(leaf).apps
        PlayerRole = apps.get_model('rosters', 'PlayerRole')
        StaffRole = apps.get_model('rosters', 'StaffRole')

        role = PlayerRole.objects.get()
        self.assertEqual((role.identity_id, role.jersey_number, role.position), (self.identity_id, 13, 'setter'))
        self.assertEqual(
            sorted(StaffRole.objects.filter(identity_id=self.identity_id).values_list('role', flat=True)),
            ['delegate', 'head_coach'],
        )

    def test_rollback_with_data_restores_team(self):
        self.executor.loader.build_graph()
        self.executor.migrate(self.executor.loader.graph.leaf_nodes('rosters'))
        self.executor.loader.build_graph()
        self.executor.migrate([self.migrate_from])
        apps = self.executor.loader.project_state([self.migrate_from]).apps
        role = apps.get_model('rosters', 'PlayerRole').objects.get()
        self.assertEqual(role.team.federation_id, '10')
