from datetime import timedelta
import io
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone
from PIL import Image
import pypdf

from ilovevoley.competitions.models import League, Match, MatchActaPhoto
from ilovevoley.competitions.services.acta_photo import (
    download_and_prepare_acta_photo,
    extract_image_from_pdf,
    process_acta_photos_from_html,
)
from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.teams.models import Club, Team


class MatchActaPhotoScrapingTests(TestCase):
    """
    Protege la regla de negocio de captura e idempotencia de actas manuales (foto):
    asegura que solo los partidos de equipos pertenecientes a tenants activos sin acta HTML
    se registran como pendientes de descarga en MatchActaPhoto, ignorando URLs no conformes
    y evitando duplicar o sobreescribir actas ya aprobadas.
    """

    def setUp(self):
        self.season = Season.objects.create(name='2025-26', is_current=True)
        self.category = Category.objects.create(name='Infantil Femenino')

        # Tenant club y organización
        self.tenant_club = Club.objects.create(federation_id='100', official_name='CLUB ESPORTIU SANT JOSEP OBRER')
        self.org, _ = Organization.objects.update_or_create(
            slug='santjosep',
            defaults={
                'name': 'Sant Josep',
                'club': self.tenant_club,
                'is_active': True,
                'club_team_names': {'Infantil': 'SANT JOSEP'},
            },
        )

        # Club rival (no tenant)
        self.rival_club = Club.objects.create(federation_id='200', official_name='CLUB VOLEIBOL MURO')
        self.other_club = Club.objects.create(federation_id='300', official_name='CLUB VOLEIBOL MANACOR')

        # Equipos
        self.tenant_team = Team.objects.create(
            name='CV SANT JOSEP',
            federation_id='team_sant_josep',
            club=self.tenant_club,
            category=self.category,
            is_active=True,
        )
        self.rival_team = Team.objects.create(
            name='VOLEI MURO',
            federation_id='team_muro',
            club=self.rival_club,
            category=self.category,
            is_active=True,
        )
        self.other_team = Team.objects.create(
            name='CV MANACOR',
            federation_id='team_manacor',
            club=self.other_club,
            category=self.category,
            is_active=True,
        )

        self.league = League.objects.create(
            name='Liga Infantil',
            season=self.season,
            federation_id='8231',
        )

        # Partidos
        now = timezone.now()
        self.match_tenant_photo = Match.objects.create(
            league=self.league,
            home_team=self.tenant_team,
            away_team=self.rival_team,
            federation_id='85271',
            round_number=1,
            match_date=now,
        )
        self.match_tenant_html = Match.objects.create(
            league=self.league,
            home_team=self.tenant_team,
            away_team=self.rival_team,
            federation_id='85272',
            round_number=1,
            match_date=now + timedelta(days=1),
        )
        self.match_non_tenant = Match.objects.create(
            league=self.league,
            home_team=self.rival_team,
            away_team=self.other_team,
            federation_id='85273',
            round_number=1,
            match_date=now + timedelta(days=2),
        )

    def test_creates_single_record_for_tenant_photo_only_match(self):
        """(a) Crea 1 registro pending_download para un partido de tenant que solo tiene foto."""
        html = """
        <div class='info_partido'>
          <div class='top'><span class='fecha'>18/10/2025</span></div>
          <div class='datos_partido'>
            <span class='nombreEquipo'>CV SANT JOSEP</span>
            <span class='nombreEquipo'>VOLEI MURO</span>
          </div>
          <div class='estado_partido' id='finalizado'>
            <span class='marcador'>25-10/25-15/25-20</span>
            <a target='_blank' href='https://www.voleibolib.net/pdf.asp?o=85271.jpg' title='Ver Foto Acta'><i class='fa fa-file-image-o fa-2x'></i></a>
          </div>
        </div>
        """
        created = process_acta_photos_from_html(html, league=self.league, round_number=1)
        self.assertEqual(created, 1)

        photo = MatchActaPhoto.objects.get(match=self.match_tenant_photo)
        self.assertEqual(photo.status, 'pending_download')
        self.assertEqual(photo.source_url, 'https://www.voleibolib.net/pdf.asp?o=85271.jpg')

    def test_does_not_create_photo_when_match_has_html_acta(self):
        """(b) No crea registro si el partido tiene enlace 'Ver Acta' o acta_html en BD."""
        html_with_acta_link = """
        <div class='info_partido'>
          <div class='top'><span class='fecha'>18/10/2025</span></div>
          <div class='datos_partido'>
            <span class='nombreEquipo'>CV SANT JOSEP</span>
            <span class='nombreEquipo'>VOLEI MURO</span>
          </div>
          <div class='estado_partido' id='finalizado'>
            <span class='marcador'>25-10/25-15/25-20</span>
            <a target='_blank' href='https://voleibolib.federatio.com/actas/85272/acta.html' title='Ver Acta'><i class='fa fa-file fa-2x'></i></a>
            <a target='_blank' href='https://www.voleibolib.net/pdf.asp?o=85272.jpeg' title='Ver Foto Acta'><i class='fa fa-file-image-o fa-2x'></i></a>
          </div>
        </div>
        """
        created = process_acta_photos_from_html(html_with_acta_link, league=self.league, round_number=1)
        self.assertEqual(created, 0)
        self.assertFalse(MatchActaPhoto.objects.filter(match=self.match_tenant_html).exists())

        # Si el partido en base de datos ya tenía acta_html, tampoco se crea aunque el HTML solo traiga foto
        self.match_tenant_photo.acta_html = 'https://voleibolib.federatio.com/actas/85271/acta.html'
        self.match_tenant_photo.save(update_fields=['acta_html'])

        html_photo_only = """
        <div class='info_partido'>
          <div class='datos_partido'>
            <span class='nombreEquipo'>CV SANT JOSEP</span>
            <span class='nombreEquipo'>VOLEI MURO</span>
          </div>
          <div class='estado_partido' id='finalizado'>
            <a target='_blank' href='https://www.voleibolib.net/pdf.asp?o=85271.jpg' title='Ver Foto Acta'></a>
          </div>
        </div>
        """
        created_retry = process_acta_photos_from_html(html_photo_only, league=self.league, round_number=1)
        self.assertEqual(created_retry, 0)
        self.assertFalse(MatchActaPhoto.objects.filter(match=self.match_tenant_photo).exists())

    def test_does_not_create_photo_for_non_tenant_match(self):
        """(c) No se crea registro para partidos cuyos equipos no pertenecen a ningún tenant activo."""
        html = """
        <div class='info_partido'>
          <div class='top'><span class='fecha'>18/10/2025</span></div>
          <div class='datos_partido'>
            <span class='nombreEquipo'>VOLEI MURO</span>
            <span class='nombreEquipo'>CV MANACOR</span>
          </div>
          <div class='estado_partido' id='finalizado'>
            <span class='marcador'>25-10/25-15/25-20</span>
            <a target='_blank' href='https://www.voleibolib.net/pdf.asp?o=85273.jpeg' title='Ver Foto Acta'></a>
          </div>
        </div>
        """
        created = process_acta_photos_from_html(html, league=self.league, round_number=1)
        self.assertEqual(created, 0)
        self.assertFalse(MatchActaPhoto.objects.filter(match=self.match_non_tenant).exists())

    def test_idempotent_scraping_does_not_duplicate_or_overwrite_approved(self):
        """(d) Repetir el scraping no duplica registros ni modifica el estado si ya está 'approved'."""
        html = """
        <div class='info_partido'>
          <div class='datos_partido'>
            <span class='nombreEquipo'>CV SANT JOSEP</span>
            <span class='nombreEquipo'>VOLEI MURO</span>
          </div>
          <div class='estado_partido' id='finalizado'>
            <a target='_blank' href='https://www.voleibolib.net/pdf.asp?o=85271.jpg' title='Ver Foto Acta'></a>
          </div>
        </div>
        """
        # Primera ejecución crea
        process_acta_photos_from_html(html, league=self.league, round_number=1)
        self.assertEqual(MatchActaPhoto.objects.filter(match=self.match_tenant_photo).count(), 1)

        # Marcamos como approved
        photo = MatchActaPhoto.objects.get(match=self.match_tenant_photo)
        photo.status = 'approved'
        photo.save(update_fields=['status'])

        # Segunda ejecución no duplica ni pisa el estado approved
        process_acta_photos_from_html(html, league=self.league, round_number=1)
        self.assertEqual(MatchActaPhoto.objects.filter(match=self.match_tenant_photo).count(), 1)
        photo.refresh_from_db()
        self.assertEqual(photo.status, 'approved')

    def test_ignores_non_conforming_url_format(self):
        """Descarta URLs del tipo o=1780153395_6042.pdf que no siguen pdf.asp?o=<número>.<ext>."""
        html = """
        <div class='info_partido'>
          <div class='datos_partido'>
            <span class='nombreEquipo'>CV SANT JOSEP</span>
            <span class='nombreEquipo'>VOLEI MURO</span>
          </div>
          <div class='estado_partido' id='finalizado'>
            <a target='_blank' href='https://www.voleibolib.net/pdf.asp?o=1780153395_6042.pdf' title='Ver Foto Acta'></a>
          </div>
        </div>
        """
        created = process_acta_photos_from_html(html, league=self.league, round_number=1)
        self.assertEqual(created, 0)
        self.assertFalse(MatchActaPhoto.objects.filter(match=self.match_tenant_photo).exists())


class ActaPhotoExtractionTests(TestCase):
    """
    Protege la decodificación y normalización de actas manuales desde PDF:
    verifica la extracción de JPEG, deduplicación de páginas repetidas, conversión
    de PNG con transparencia a RGB limpio (~1600px, sin EXIF) y detección de respuestas
    caducadas o sin imagen sin fallar el proceso.
    """

    @staticmethod
    def _make_jpeg_pdf(width=2000, height=1000):
        img = Image.new('RGB', (width, height), color=(120, 150, 180))
        buf = io.BytesIO()
        img.save(buf, format='PDF')
        return buf.getvalue()

    @staticmethod
    def _make_two_page_identical_pdf(width=1000, height=800):
        img = Image.new('RGB', (width, height), color=(200, 120, 80))
        buf = io.BytesIO()
        img.save(buf, format='PDF')
        r = pypdf.PdfReader(io.BytesIO(buf.getvalue()))
        w = pypdf.PdfWriter()
        w.add_page(r.pages[0])
        w.add_page(r.pages[0])
        out = io.BytesIO()
        w.write(out)
        return out.getvalue()

    @staticmethod
    def _make_png_with_mask_pdf(width=800, height=600):
        img = Image.new('RGBA', (width, height), color=(50, 100, 150, 180))
        buf = io.BytesIO()
        img.save(buf, format='PDF')
        return buf.getvalue()

    @staticmethod
    def _make_blank_pdf():
        w = pypdf.PdfWriter()
        w.add_blank_page(width=600, height=800)
        out = io.BytesIO()
        w.write(out)
        return out.getvalue()

    @staticmethod
    def _make_expired_text_response():
        return b'El acta no se ha guardado en el servidor.Consulte con la federacion.'

    def test_extract_normal_jpeg_pdf_scales_down_and_strips_exif(self):
        """Extrae JPEG normal de PDF, escala lado largo a 1600 px y descarta metadatos EXIF."""
        pdf_bytes = self._make_jpeg_pdf(2000, 1000)
        jpeg_bytes, status = extract_image_from_pdf(pdf_bytes)

        self.assertEqual(status, 'ok')
        self.assertIsNotNone(jpeg_bytes)

        out_img = Image.open(io.BytesIO(jpeg_bytes))
        self.assertEqual(out_img.format, 'JPEG')
        self.assertEqual(out_img.mode, 'RGB')
        self.assertEqual(out_img.size, (1600, 800))
        self.assertEqual(out_img.getexif(), {})

    def test_extract_two_identical_pages_deduplicates(self):
        """PDF con dos páginas que contienen la misma imagen se extrae deduplicado."""
        pdf_bytes = self._make_two_page_identical_pdf(1000, 800)
        jpeg_bytes, status = extract_image_from_pdf(pdf_bytes)

        self.assertEqual(status, 'ok')
        out_img = Image.open(io.BytesIO(jpeg_bytes))
        self.assertEqual(out_img.size, (1000, 800))
        self.assertEqual(out_img.mode, 'RGB')

    def test_extract_png_with_mask_converts_to_rgb(self):
        """PDF con PNG y canal alfa se convierte correctamente a RGB sin romper el flujo."""
        pdf_bytes = self._make_png_with_mask_pdf(800, 600)
        jpeg_bytes, status = extract_image_from_pdf(pdf_bytes)

        self.assertEqual(status, 'ok')
        out_img = Image.open(io.BytesIO(jpeg_bytes))
        self.assertEqual(out_img.format, 'JPEG')
        self.assertEqual(out_img.mode, 'RGB')

    def test_extract_pdf_without_images_returns_unreadable(self):
        """PDF sin ninguna imagen (ej. HEIC no procesado) devuelve estado 'unreadable'."""
        pdf_bytes = self._make_blank_pdf()
        jpeg_bytes, status = extract_image_from_pdf(pdf_bytes)

        self.assertEqual(status, 'unreadable')
        self.assertIsNone(jpeg_bytes)

    def test_extract_expired_text_response_returns_expired(self):
        """Respuesta que no es PDF (texto 'El acta no se ha guardado...') devuelve 'expired'."""
        text_bytes = self._make_expired_text_response()
        jpeg_bytes, status = extract_image_from_pdf(text_bytes)

        self.assertEqual(status, 'expired')
        self.assertIsNone(jpeg_bytes)


class ActaPhotoDownloadTests(TestCase):
    """
    Protege el servicio de descarga y persistencia de MatchActaPhoto:
    asocia la imagen al modelo, transiciona a 'expired' o 'unreadable' en caso de error
    y respeta el estado de actas ya aprobadas.
    """

    def setUp(self):
        self.season = Season.objects.create(name='2025-26', is_current=True)
        self.category = Category.objects.create(name='Infantil')
        self.club = Club.objects.create(federation_id='100', official_name='CLUB SANT JOSEP')
        self.team = Team.objects.create(name='SANT JOSEP', federation_id='t1', club=self.club, category=self.category, is_active=True)
        self.rival = Team.objects.create(name='RIVAL', federation_id='t2', category=self.category, is_active=True)
        self.league = League.objects.create(name='Liga', season=self.season, federation_id='8000')
        self.match = Match.objects.create(
            league=self.league,
            home_team=self.team,
            away_team=self.rival,
            federation_id='85271',
            round_number=1,
            match_date=timezone.now(),
        )
        self.photo = MatchActaPhoto.objects.create(
            match=self.match,
            source_url='https://www.voleibolib.net/pdf.asp?o=85271.jpg',
            status='pending_download',
        )

    @patch('requests.get')
    def test_download_success_saves_image_file(self, mock_get):
        """Descarga exitosa guarda el fichero JPEG normalizado en photo.image."""
        pdf_bytes = ActaPhotoExtractionTests._make_jpeg_pdf(1000, 800)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = pdf_bytes
        mock_get.return_value = mock_response

        ok = download_and_prepare_acta_photo(self.photo)
        self.assertTrue(ok)

        self.photo.refresh_from_db()
        self.assertTrue(bool(self.photo.image))
        self.assertTrue(self.photo.image.name.endswith('.jpg'))

    def test_download_transient_failure_keeps_photo_pending(self):
        """Un timeout o un 5xx de la federación no marca la foto como caducada: se reintenta en el siguiente ciclo."""
        import requests

        server_error = MagicMock(status_code=503)
        for label, patcher in (
            ('timeout', patch('requests.get', side_effect=requests.exceptions.Timeout('lento'))),
            ('503', patch('requests.get', return_value=server_error)),
        ):
            with self.subTest(label), patcher:
                self.assertFalse(download_and_prepare_acta_photo(self.photo))

                self.photo.refresh_from_db()
                self.assertEqual(self.photo.status, 'pending_download')

    @patch('requests.get')
    def test_download_expired_marks_status_expired(self, mock_get):
        """Descarga de acta caducada actualiza el estado a 'expired'."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'El acta no se ha guardado en el servidor.'
        mock_get.return_value = mock_response

        ok = download_and_prepare_acta_photo(self.photo)
        self.assertFalse(ok)

        self.photo.refresh_from_db()
        self.assertEqual(self.photo.status, 'expired')

    @patch('requests.get')
    def test_download_unreadable_marks_status_unreadable(self, mock_get):
        """Descarga de PDF sin imágenes actualiza el estado a 'unreadable'."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = ActaPhotoExtractionTests._make_blank_pdf()
        mock_get.return_value = mock_response

        ok = download_and_prepare_acta_photo(self.photo)
        self.assertFalse(ok)

        self.photo.refresh_from_db()
        self.assertEqual(self.photo.status, 'unreadable')

    def test_download_skips_approved_photo(self):
        """Acta ya aprobada no se sobreescribe ni se descarga."""
        self.photo.status = 'approved'
        self.photo.save(update_fields=['status'])

        ok = download_and_prepare_acta_photo(self.photo)
        self.assertFalse(ok)

        self.photo.refresh_from_db()
        self.assertEqual(self.photo.status, 'approved')
