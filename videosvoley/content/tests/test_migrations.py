from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class ContentSeasonBackfillMigrationTest(TransactionTestCase):
    """Image.year y Video sin temporada -> FK, sin perder la referencia de temporada."""

    migrate_from = ('content', '0003_alter_image_categories_alter_video_category')
    migrate_to = ('content', '0004_remove_image_videos_imag_year_e48770_idx_and_more')

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_from])
        self.executor.loader.build_graph()

        old_apps = self.executor.loader.project_state([self.migrate_from]).apps
        leaf_apps = self.executor.loader.project_state(self.executor.loader.graph.leaf_nodes()).apps

        Season = leaf_apps.get_model('core', 'Season')
        League = leaf_apps.get_model('competitions', 'League')
        Match = leaf_apps.get_model('competitions', 'Match')
        Team = leaf_apps.get_model('teams', 'Team')
        User = leaf_apps.get_model('users', 'User')

        season = Season.objects.create(name='2024-25', start_year=2024, end_year=2025)
        league = League.objects.create(name='Liga BF', federation_id='L-BF', season=season)
        team = Team.objects.create(name='Equipo BF', federation_id='T-BF')
        match = Match.objects.create(
            league=league, home_team=team, away_team=team,
            match_date=timezone.now(), federation_id='M-BF',
        )
        user = User.objects.create(username='backfill-user')

        Image = old_apps.get_model('content', 'Image')
        Video = old_apps.get_model('content', 'Video')
        Image.objects.create(
            image='a.jpg', title='Con partido', uploaded_by_id=user.id, year=2024, match_id=match.id,
        )
        Image.objects.create(
            image='b.jpg', title='Sin partido', uploaded_by_id=user.id, year=2020,
        )
        Video.objects.create(
            title='Con partido', youtube_url='https://youtu.be/a', created_by_id=user.id, match_id=match.id,
        )
        Video.objects.create(
            title='Sin partido', youtube_url='https://youtu.be/b', created_by_id=user.id,
        )

    def tearDown(self):
        self.executor.loader.build_graph()
        self.executor.migrate(self.executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_backfill(self):
        self.executor.loader.build_graph()
        self.executor.migrate([self.migrate_to])
        new_apps = self.executor.loader.project_state([self.migrate_to]).apps
        Image = new_apps.get_model('content', 'Image')
        Video = new_apps.get_model('content', 'Video')

        img_match = Image.objects.get(title='Con partido')
        img_free = Image.objects.get(title='Sin partido')
        video_match = Video.objects.get(title='Con partido')
        video_free = Video.objects.get(title='Sin partido')

        self.assertEqual(img_match.season.name, '2024-25')
        self.assertEqual(video_match.season.name, '2024-25')
        # Sin partido: se infiere de la fecha de subida (hoy).
        self.assertIsNotNone(img_free.season_id)
        self.assertIsNotNone(video_free.season_id)
