"""Tests para la lógica de nombrado descriptivo de imágenes y prevención de colisiones.

Justificación según docs/ai-guidelines/testing-guidelines.md:
- Protege una regla de negocio del producto: formato descriptivo de nombres de fotos
  para partidos, álbumes y fotos sueltas (#494).
- Verifica transformaciones de datos no triviales: sanitización de nombres, caracteres
  especiales en catalán/castellano y normalización de slugs para storage.
- Comprueba manejo de colisiones e idempotencia al asignar secuenciales en storage.
"""
from datetime import date
from unittest.mock import MagicMock

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from ilovevoley.competitions.models import Match
from ilovevoley.content.image_naming import (
    build_descriptive_storage_path,
    build_descriptive_title,
    get_image_upload_path,
    get_next_sequence_number,
)
from ilovevoley.content.models import Image
from ilovevoley.core.models import Organization, Season
from ilovevoley.teams.models import Club, Team
from ilovevoley.users.models import User


class ImageNamingTests(TestCase):
    def setUp(self):
        import shutil
        import tempfile
        from django.test import override_settings

        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        self.org, _ = Organization.objects.get_or_create(slug='namingclub', defaults={'name': 'Naming Club'})
        self.user = User.objects.create_user(username='tester_naming', password='pass')
        self.season = Season.objects.current() or Season.objects.create(
            name='2026-27',
            code='2026-27',
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 30),
            is_current=True,
        )
        self.club = Club.objects.create(official_name='CV Sant Josep Naming', federation_id='SJ99')
        self.home_team = Team.objects.create(name='CV Sant Josep Senior A', federation_id='TEAM_SJ_1', club=self.club)
        self.away_team = Team.objects.create(name='CV Pòrtol', federation_id='TEAM_PORTOL_1', club=self.club)
        self.match = Match.objects.create(
            home_team=self.home_team,
            away_team=self.away_team,
            match_date=date(2026, 10, 11),
        )

    def test_build_descriptive_title_for_match(self):
        """El título de una imagen de partido debe incluir equipos, fecha y secuencial."""
        title = build_descriptive_title(match=self.match, seq=1)
        self.assertEqual(title, 'CV Sant Josep Senior A vs CV Pòrtol - 11/10/2026 - 001')

    def test_build_descriptive_title_for_album(self):
        """El título de una imagen de álbum debe incluir el nombre del álbum y secuencial."""
        title = build_descriptive_title(album_name='Celebración Copa Balear', seq=2)
        self.assertEqual(title, 'Celebración Copa Balear - 002')

    def test_build_descriptive_title_for_loose_photo(self):
        """El título de una foto suelta con título base debe incluir el título y secuencial opcional."""
        title_with_seq = build_descriptive_title(base_title='Entrenamiento Juvenil', seq=3)
        self.assertEqual(title_with_seq, 'Entrenamiento Juvenil - 003')

        title_single = build_descriptive_title(base_title='Entrenamiento Juvenil')
        self.assertEqual(title_single, 'Entrenamiento Juvenil')

    def test_build_descriptive_storage_path_for_match(self):
        """El fichero en storage de un partido debe tener un slug limpio con equipos, fecha y secuencial."""
        path = build_descriptive_storage_path(
            match=self.match,
            seq=1,
            extension='jpg',
            now_date=date(2026, 10, 15),
        )
        self.assertEqual(
            path,
            'images/2026/10/cv-sant-josep-senior-a-vs-cv-portol-2026-10-11-001.jpg',
        )

    def test_build_descriptive_storage_path_for_album(self):
        """El fichero en storage de un álbum debe usar el slug del álbum y secuencial."""
        path = build_descriptive_storage_path(
            album_name='Celebración Final',
            seq=5,
            extension='png',
            now_date=date(2026, 10, 15),
        )
        self.assertEqual(
            path,
            'images/2026/10/celebracion-final-005.png',
        )

    def test_accents_and_special_characters_are_sanitized(self):
        """Caracteres especiales (apóstrofes, acentos, eñes) deben normalizarse correctamente en slugs."""
        team_catalan = Team.objects.create(name="L'Illa Grau Vóley", federation_id='TEAM_CAT_1', club=self.club)
        match = Match.objects.create(
            home_team=team_catalan,
            away_team=self.away_team,
            match_date=date(2026, 11, 20),
        )
        path = build_descriptive_storage_path(
            match=match,
            seq=1,
            extension='JPG',
            now_date=date(2026, 11, 20),
        )
        self.assertEqual(
            path,
            'images/2026/11/l-illa-grau-voley-vs-cv-portol-2026-11-20-001.jpg',
        )

    def test_get_next_sequence_number_from_db(self):
        """El secuencial debe calcularse sumando 1 a las imágenes existentes del contexto."""
        from io import BytesIO
        from PIL import Image as PILImage

        # Inicialmente 1
        seq = get_next_sequence_number(match=self.match)
        self.assertEqual(seq, 1)

        # Crear una imagen válida para el partido
        img = PILImage.new('RGB', (20, 20), color='red')
        buf = BytesIO()
        img.save(buf, format='JPEG')
        buf.seek(0)
        uploaded = SimpleUploadedFile('test1.jpg', buf.read(), content_type='image/jpeg')

        Image.objects.create(
            title='Foto previa',
            match=self.match,
            uploaded_by=self.user,
            organization=self.org,
            image=uploaded,
        )

        seq_after = get_next_sequence_number(match=self.match)
        self.assertEqual(seq_after, 2)

    def test_storage_collision_avoidance_increments_sequence(self):
        """Si un fichero ya existe en storage, se debe buscar el siguiente secuencial no ocupado."""
        mock_storage = MagicMock()
        # Simular que el -001 ya existe pero el -002 no
        mock_storage.exists.side_effect = lambda p: p.endswith('-001.jpg')

        path = build_descriptive_storage_path(
            match=self.match,
            seq=1,
            extension='jpg',
            storage=mock_storage,
            now_date=date(2026, 10, 15),
        )
        self.assertTrue(path.endswith('-002.jpg'))

    def test_get_image_upload_path_fallback_when_instance_none(self):
        """Si instance es None, debe mantener compatibilidad generando un UUID."""
        import uuid
        path = get_image_upload_path(None, 'cam_001.jpg')
        parts = path.split('/')
        self.assertEqual(parts[0], 'images')
        filename = parts[-1]
        base_name, ext = filename.split('.')
        self.assertEqual(ext, 'jpg')
        # Verificar que es un UUID válido
        self.assertEqual(uuid.UUID(base_name).hex, base_name)

    def test_is_generic_camera_filename(self):
        """Verifica la detección de nombres automáticos de cámara y UUIDs."""
        from ilovevoley.content.image_naming import is_generic_camera_filename

        self.assertTrue(is_generic_camera_filename('IMG_2989'))
        self.assertTrue(is_generic_camera_filename('DSC_0042'))
        self.assertTrue(is_generic_camera_filename('DSC0042'))
        self.assertTrue(is_generic_camera_filename('DSCN1234'))
        self.assertTrue(is_generic_camera_filename('P1010023'))
        self.assertTrue(is_generic_camera_filename('SAM_1234'))
        self.assertTrue(is_generic_camera_filename('3faf37d3-b5de-4c95-b257-70c91076a012'))
        self.assertTrue(is_generic_camera_filename(''))
        self.assertTrue(is_generic_camera_filename('   '))

        self.assertFalse(is_generic_camera_filename('CV Sant Josep vs CIDE'))
        self.assertFalse(is_generic_camera_filename('Celebración Final'))
        self.assertFalse(is_generic_camera_filename('Remate de Marc'))

    def test_image_save_auto_populates_title_for_match(self):
        """Al guardar una imagen vinculada a partido con título genérico, se auto-asigna título descriptivo."""
        from io import BytesIO
        from PIL import Image as PILImage

        img = PILImage.new('RGB', (20, 20), color='green')
        buf = BytesIO()
        img.save(buf, format='JPEG')
        buf.seek(0)
        uploaded = SimpleUploadedFile('IMG_9999.JPG', buf.read(), content_type='image/jpeg')

        image = Image.objects.create(
            title='IMG_9999',
            match=self.match,
            uploaded_by=self.user,
            organization=self.org,
            image=uploaded,
        )

        self.assertEqual(image.title, 'CV Sant Josep Senior A vs CV Pòrtol - 11/10/2026 - 001')
        self.assertTrue(
            image.image.name.endswith('cv-sant-josep-senior-a-vs-cv-portol-2026-10-11-001.jpg'),
            f"Expected ending with cv-sant-josep-senior-a-vs-cv-portol-2026-10-11-001.jpg, got: {image.image.name}",
        )

    def test_image_save_auto_populates_title_for_album(self):
        """Al guardar una imagen vinculada a álbum con título genérico, se auto-asigna título descriptivo."""
        import uuid
        from io import BytesIO
        from PIL import Image as PILImage

        img = PILImage.new('RGB', (20, 20), color='yellow')
        buf = BytesIO()
        img.save(buf, format='JPEG')
        buf.seek(0)
        uploaded = SimpleUploadedFile('DSC_0001.JPG', buf.read(), content_type='image/jpeg')

        album_id = uuid.uuid4()
        image = Image.objects.create(
            title='DSC_0001',
            album_name='Copa Balear 2026',
            album_group_id=album_id,
            uploaded_by=self.user,
            organization=self.org,
            image=uploaded,
        )

        self.assertEqual(image.title, 'Copa Balear 2026 - 001')
        self.assertTrue(image.image.name.endswith('copa-balear-2026-001.jpg'))

    def test_image_save_preserves_custom_title(self):
        """Si el usuario introduce un título personalizado (no genérico), se respeta."""
        from io import BytesIO
        from PIL import Image as PILImage

        img = PILImage.new('RGB', (20, 20), color='purple')
        buf = BytesIO()
        img.save(buf, format='JPEG')
        buf.seek(0)
        uploaded = SimpleUploadedFile('custom.jpg', buf.read(), content_type='image/jpeg')

        image = Image.objects.create(
            title='Gran bloqueo defensivo',
            match=self.match,
            uploaded_by=self.user,
            organization=self.org,
            image=uploaded,
        )

        self.assertEqual(image.title, 'Gran bloqueo defensivo')

