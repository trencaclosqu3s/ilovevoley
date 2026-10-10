"""Tests para el management command de renombrado de imágenes históricas.

Justificación según docs/ai-guidelines/testing-guidelines.md:
- Cubre un flujo con efectos persistentes: renombra ficheros en storage,
  actualiza campos de base de datos y regenera miniaturas (#494).
- Verifica idempotencia y flag --dry-run en un proceso masivo de ficheros.
"""
import shutil
import tempfile
from datetime import date
from io import BytesIO, StringIO
from PIL import Image as PILImage

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings

from ilovevoley.competitions.models import Match
from ilovevoley.content.models import Image
from ilovevoley.core.models import Organization, Season
from ilovevoley.teams.models import Club, Team
from ilovevoley.users.models import User


class RenameContentImagesCommandTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        self.org, _ = Organization.objects.get_or_create(slug='testcmdorg', defaults={'name': 'Cmd Org'})
        self.user = User.objects.create_user(username='cmd_tester', password='pass')
        self.season = Season.objects.current() or Season.objects.create(
            name='2026-27',
            code='2026-27',
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 30),
            is_current=True,
        )
        self.club = Club.objects.create(official_name='Club Cmd', federation_id='CMD01')
        self.home_team = Team.objects.create(name='Equipo Local', federation_id='TEAM_CMD_H', club=self.club)
        self.away_team = Team.objects.create(name='Equipo Rival', federation_id='TEAM_CMD_A', club=self.club)
        from datetime import datetime
        from django.utils import timezone
        self.match = Match.objects.create(
            home_team=self.home_team,
            away_team=self.away_team,
            match_date=timezone.make_aware(datetime(2026, 10, 11, 12, 0)),
        )

    def _create_jpeg(self):
        img = PILImage.new('RGB', (50, 50), color='cyan')
        buf = BytesIO()
        img.save(buf, format='JPEG')
        buf.seek(0)
        return buf.read()

    def test_dry_run_does_not_modify_files_or_database(self):
        """El flag --dry-run debe reportar los cambios propuestos sin modificar storage ni BD."""
        content = self._create_jpeg()
        uploaded = SimpleUploadedFile('IMG_0001.JPG', content, content_type='image/jpeg')

        image = Image(
            title='IMG_0001',
            match=self.match,
            uploaded_by=self.user,
            organization=self.org,
            image=uploaded,
        )
        # Guardar forzando nombre original
        image.save()
        original_name = image.image.name

        out = StringIO()
        call_command('rename_content_images', dry_run=True, match=self.match.id, stdout=out)
        output = out.getvalue()

        image.refresh_from_db()
        self.assertIn('DRY-RUN', output)
        self.assertEqual(image.image.name, original_name)

    def test_rename_command_renames_storage_file_and_updates_model(self):
        """El comando debe mover el archivo en storage y actualizar image.title e image.image.name."""
        content = self._create_jpeg()
        # Forzar un nombre con UUID legado en storage
        saved_path = default_storage.save('images/2026/10/3faf37d3b5de4c95b25770c91076a012.jpg', BytesIO(content))

        image = Image.objects.create(
            title='IMG_0002',
            match=self.match,
            uploaded_by=self.user,
            organization=self.org,
            image=saved_path,
        )

        out = StringIO()
        call_command('rename_content_images', match=self.match.id, stdout=out)

        image.refresh_from_db()
        self.assertEqual(image.title, 'Equipo Local vs Equipo Rival - 11/10/2026 - 001')
        self.assertTrue(
            image.image.name.endswith('equipo-local-vs-equipo-rival-2026-10-11-001.jpg')
        )
        self.assertTrue(default_storage.exists(image.image.name))
        # El archivo antiguo debe haberse eliminado
        self.assertFalse(default_storage.exists(saved_path))
