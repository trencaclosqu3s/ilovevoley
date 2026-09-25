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


class PersonOrganizationBackfillMigrationTest(TransactionTestCase):
    """La organización se deriva de los roles (Team.club -> Organization) solo si es inequívoca."""

    migrate_from = ('rosters', '0005_remove_playerrole_unique_active_player_role_and_more')
    migrate_to = ('rosters', '0006_person_organization')

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_from])
        self.executor.loader.build_graph()
        apps = self.executor.loader.project_state([self.migrate_from]).apps
        leaf_apps = self.executor.loader.project_state(self.executor.loader.graph.leaf_nodes()).apps

        Club = leaf_apps.get_model('teams', 'Club')
        Team = leaf_apps.get_model('teams', 'Team')
        Organization = leaf_apps.get_model('core', 'Organization')
        Person = apps.get_model('rosters', 'Person')
        PlayerRole = apps.get_model('rosters', 'PlayerRole')
        StaffRole = apps.get_model('rosters', 'StaffRole')
        Season = leaf_apps.get_model('core', 'Season')

        club_a = Club.objects.create(federation_id='CLUB-A', official_name='Club A')
        club_b = Club.objects.create(federation_id='CLUB-B', official_name='Club B')
        org_a = Organization.objects.create(slug='org-a', name='Org A', club=club_a)
        org_b = Organization.objects.create(slug='org-b', name='Org B', club=club_b)
        team_a = Team.objects.create(name='Equipo A', federation_id='TEAM-A', club=club_a)
        team_b = Team.objects.create(name='Equipo B', federation_id='TEAM-B', club=club_b)
        season = Season.objects.create(name='2025-26', start_year=2025, end_year=2026)

        person_a = Person.objects.create(first_name='Ana', last_name='ClubA')
        person_b = Person.objects.create(first_name='Beto', last_name='ClubB')
        person_none = Person.objects.create(first_name='Sin', last_name='Roles')
        person_mixed = Person.objects.create(first_name='Mixta', last_name='DosClubes')
        PlayerRole.objects.create(person_id=person_a.id, team_id=team_a.id, season_id=season.id)
        StaffRole.objects.create(
            person_id=person_b.id, team_id=team_b.id, role='head_coach', season_id=season.id,
        )
        # Roles en dos clubes: pertenencia ambigua, no se asigna.
        PlayerRole.objects.create(person_id=person_mixed.id, team_id=team_a.id, season_id=season.id)
        StaffRole.objects.create(
            person_id=person_mixed.id, team_id=team_b.id, role='delegate', season_id=season.id,
        )

        self.org_a_id = org_a.id
        self.org_b_id = org_b.id
        self.person_ids = [person_a.id, person_b.id, person_none.id, person_mixed.id]

    def tearDown(self):
        self.executor.loader.build_graph()
        self.executor.migrate(self.executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_backfill_asigna_organizacion_inequivoca(self):
        self.executor.loader.build_graph()
        self.executor.migrate([self.migrate_to])
        new_apps = self.executor.loader.project_state([self.migrate_to]).apps
        Person = new_apps.get_model('rosters', 'Person')

        person_a, person_b, person_none, person_mixed = (
            Person.objects.get(pk=pk) for pk in self.person_ids
        )
        self.assertEqual(person_a.organization_id, self.org_a_id)
        self.assertEqual(person_b.organization_id, self.org_b_id)
        # Sin roles resolubles o con roles en varios clubes: queda sin asignar.
        self.assertIsNone(person_none.organization_id)
        self.assertIsNone(person_mixed.organization_id)
