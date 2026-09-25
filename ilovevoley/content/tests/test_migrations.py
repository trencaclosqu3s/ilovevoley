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
        # Imagen sin partido: se respeta el antiguo `year` corregido a mano.
        self.assertEqual(img_free.season.name, '2020-21')
        # Vídeo sin partido: se infiere de la fecha de subida (hoy).
        self.assertIsNotNone(video_free.season_id)


class PurgeExifGpsMetadataMigrationTest(TransactionTestCase):
    """Verifica que la migración purgue coordenadas GPS de imágenes existentes en almacenamiento."""

    migrate_from = ('content', '0004_remove_image_videos_imag_year_e48770_idx_and_more')
    migrate_to = ('content', '0005_purge_exif_gps_metadata')

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_from])
        self.executor.loader.build_graph()

        old_apps = self.executor.loader.project_state([self.migrate_from]).apps
        leaf_apps = self.executor.loader.project_state(self.executor.loader.graph.leaf_nodes()).apps

        User = leaf_apps.get_model('users', 'User')
        user = User.objects.create(username='migration-test-user')

        Image = old_apps.get_model('content', 'Image')
        Person = leaf_apps.get_model('rosters', 'Person')

        from io import BytesIO
        from PIL import Image as PILImage
        from PIL.ExifTags import Base, GPS
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage

        img = PILImage.new('RGB', (100, 100), color='purple')
        exif = img.getexif()
        gps_ifd = exif.get_ifd(Base.GPSInfo)
        gps_ifd[GPS.GPSLatitude] = (39.5, 2.6, 0.0)
        gps_ifd[GPS.GPSLongitude] = (2.6, 39.5, 0.0)
        buf = BytesIO()
        img.save(buf, format='JPEG', exif=exif)
        buf.seek(0)

        self.img_path = default_storage.save('test_mig_img.jpg', ContentFile(buf.getvalue()))
        self.photo_path = default_storage.save('test_mig_person.jpg', ContentFile(buf.getvalue()))

        Image.objects.create(
            image=self.img_path,
            title='Foto existente con GPS',
            uploaded_by_id=user.id,
        )
        Person.objects.create(
            first_name='Lucas',
            last_name='Test',
            photo=self.photo_path,
        )

    def tearDown(self):
        from django.core.files.storage import default_storage
        if hasattr(self, 'img_path') and default_storage.exists(self.img_path):
            default_storage.delete(self.img_path)
        if hasattr(self, 'photo_path') and default_storage.exists(self.photo_path):
            default_storage.delete(self.photo_path)
        self.executor.loader.build_graph()
        self.executor.migrate(self.executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_purge_exif_gps_metadata(self):
        from PIL import Image as PILImage
        from PIL.ExifTags import Base
        from django.core.files.storage import default_storage

        self.executor.loader.build_graph()
        self.executor.migrate([self.migrate_to])

        with default_storage.open(self.img_path, 'rb') as f:
            sanitized_img = PILImage.open(f)
            self.assertEqual(dict(sanitized_img.getexif().get_ifd(Base.GPSInfo)), {})

        with default_storage.open(self.photo_path, 'rb') as f:
            sanitized_photo = PILImage.open(f)
            self.assertEqual(dict(sanitized_photo.getexif().get_ifd(Base.GPSInfo)), {})
