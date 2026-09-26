from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class MigrateVideoManagersToMembershipTest(TransactionTestCase):
    """Verifica que la migración 0011 asigna rol manager a usuarios de VideoManagers."""

    migrate_from = ('users', '0010_alter_user_preferred_categories')
    migrate_to = ('users', '0011_migrate_videomanagers_to_membership')

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_from])
        self.executor.loader.build_graph()
        old_apps = self.executor.loader.project_state([self.migrate_from]).apps
        leaf_apps = self.executor.loader.project_state(self.executor.loader.graph.leaf_nodes()).apps

        User = old_apps.get_model('users', 'User')
        Group = old_apps.get_model('auth', 'Group')
        Membership = old_apps.get_model('users', 'Membership')
        Organization = leaf_apps.get_model('core', 'Organization')
        Video = old_apps.get_model('content', 'Video')

        vm_group, _ = Group.objects.get_or_create(name='VideoManagers')

        self.org1 = Organization.objects.create(slug='club1', name='Club 1', default_home='videos')
        self.org2 = Organization.objects.create(slug='club2', name='Club 2', default_home='videos')

        # Usuario 1: en VideoManagers con membership 'member' en org1
        self.user1 = User.objects.create_user(username='vm_user1', password='pass')
        self.user1.groups.add(vm_group)
        Membership.objects.create(user=self.user1, organization_id=self.org1.id, role='member', is_approved=True)

        # Usuario 2: en VideoManagers sin membership pero con Video en org2
        self.user2 = User.objects.create_user(username='vm_user2', password='pass')
        self.user2.groups.add(vm_group)
        Video.objects.create(
            title='Video Test',
            youtube_url='https://youtu.be/test',
            created_by=self.user2,
            organization_id=self.org2.id,
        )

        # Usuario 3: usuario normal con membership 'member' (no debe cambiar)
        self.user3 = User.objects.create_user(username='normal_user', password='pass')
        Membership.objects.create(user=self.user3, organization_id=self.org1.id, role='member', is_approved=True)

    def tearDown(self):
        self.executor.loader.build_graph()
        self.executor.migrate(self.executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_videomanagers_migrated_to_manager_role(self):
        self.executor.loader.build_graph()
        self.executor.migrate([self.migrate_to])
        new_apps = self.executor.loader.project_state([self.migrate_to]).apps
        Membership = new_apps.get_model('users', 'Membership')

        # user1 debe haber sido ascendido a manager en org1
        m1 = Membership.objects.get(user_id=self.user1.id, organization_id=self.org1.id)
        self.assertEqual(m1.role, 'manager')

        # user2 debe tener una membership de manager en org2
        m2 = Membership.objects.get(user_id=self.user2.id, organization_id=self.org2.id)
        self.assertEqual(m2.role, 'manager')
        self.assertTrue(m2.is_approved)

        # user3 debe seguir siendo member
        m3 = Membership.objects.get(user_id=self.user3.id, organization_id=self.org1.id)
        self.assertEqual(m3.role, 'member')
