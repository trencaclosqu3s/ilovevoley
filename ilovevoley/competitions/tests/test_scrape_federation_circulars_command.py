import pytest
from unittest.mock import patch
from django.core.management import call_command

from ilovevoley.core.models import Category, Organization, Season
from ilovevoley.competitions.models import FederationCircular, FederationSanction

ITEMS = [
    {"Nombre": "NORMES DE COMPETICIO", "URL": "norm.pdf", "Fecha": "30/12/2025"},
    {"Nombre": "ESTAT CALENDARI", "URL": None, "Fecha": "no-es-fecha"},
]


@pytest.mark.django_db
@patch('ilovevoley.competitions.services.balearic_callups_client.fetch_balearic_circulares')
def test_scrape_circulars_is_idempotent_and_tolerates_missing_pdf_or_date(mock_fetch):
    """Segunda ejecución no duplica; circulares sin PDF o con fecha inválida se indexan igual."""
    Season.objects.create(name='2026-27', start_year=2026, end_year=2027, is_current=True)
    mock_fetch.return_value = ITEMS

    call_command('scrape_federation_circulars', season='2026-27', tipo=[11])
    call_command('scrape_federation_circulars', season='2026-27', tipo=[11])

    assert FederationCircular.objects.count() == 2
    sin_pdf = FederationCircular.objects.get(title='ESTAT CALENDARI')
    assert sin_pdf.file_name == '' and sin_pdf.circular_date is None and sin_pdf.pdf_url == ''
    assert FederationCircular.objects.get(title='NORMES DE COMPETICIO').pdf_url.endswith('/upload/descargas/norm.pdf')


@pytest.mark.django_db
@patch('ilovevoley.competitions.services.balearic_callups_client.fetch_balearic_circulares')
def test_scrape_circulars_dry_run_does_not_write(mock_fetch):
    Season.objects.create(name='2026-27', start_year=2026, end_year=2027, is_current=True)
    mock_fetch.return_value = ITEMS

    call_command('scrape_federation_circulars', season='2026-27', dry_run=True)

    assert FederationCircular.objects.count() == 0
    assert [c.kwargs['tipo'] for c in mock_fetch.call_args_list] == [6, 11, 8]


PDF_TEXT = """INFRACCIONES Y SANCIONES Temporada 2025-26
FECHA CATEGORÍA GRUPO INFRACTOR INFRACCIÓN SANCIÓN
4/11/25 Infantil Femenina 1ª Div. Espectador Sr.R.
CV Sant Josep Groc ACTOS DE COACCIÓN Prohibición asistencia 3 jornadas
3/11/25 2ª Nacional Masculina CV Ciutadella Biosport ALINEACIÓN INDEBIDA Pérdida de partido (0-3)
Federación de Voleibol de les Illes Balears
Comité de Competición de la FVBIB"""


@pytest.mark.django_db
@patch('ilovevoley.competitions.services.circulars_ingestion._pdf_text', return_value=PDF_TEXT)
@patch('ilovevoley.competitions.services.balearic_callups_client.download_callup_pdf')
@patch('ilovevoley.competitions.services.balearic_callups_client.fetch_balearic_circulares')
def test_disciplinary_keeps_only_tenant_rows_and_reads_pdf_once(mock_fetch, mock_download, _mock_text):
    """Solo se guardan las filas que mencionan a un equipo del tenant (con su categoría
    guardada) y un PDF ya procesado no se vuelve a descargar."""
    Season.objects.create(name='2026-27', start_year=2026, end_year=2027, is_current=True)
    org, _ = Organization.objects.update_or_create(slug='santjosep', defaults={'club_team_names': {'Infantil': 'SANT JOSEP'}})
    infantil, _ = Category.objects.get_or_create(name='Infantil')
    Category.objects.get_or_create(name='Cadete')
    mock_fetch.return_value = [{"Nombre": "RESOLUCIONES 1", "URL": "disc.pdf", "Fecha": "10/11/2025"}]
    mock_download.return_value = (b'%PDF', 'sha')

    call_command('scrape_federation_circulars', season='2026-27', tipo=[6])
    call_command('scrape_federation_circulars', season='2026-27', tipo=[6])

    sanction = FederationSanction.objects.get()
    assert (sanction.organization, sanction.category) == (org, infantil)
    assert 'Ciutadella' not in sanction.text and 'Federación de Voleibol' not in sanction.text
    assert str(sanction.sanction_date) == '2025-11-04'
    assert mock_download.call_count == 1


@pytest.mark.django_db
@patch('ilovevoley.competitions.services.circulars_ingestion._pdf_text', side_effect=ValueError('pdf roto'))
@patch('ilovevoley.competitions.services.balearic_callups_client.download_callup_pdf')
@patch('ilovevoley.competitions.services.balearic_callups_client.fetch_balearic_circulares')
def test_disciplinary_unreadable_pdf_is_retried_next_run(mock_fetch, mock_download, _mock_text):
    Season.objects.create(name='2026-27', start_year=2026, end_year=2027, is_current=True)
    Organization.objects.update_or_create(slug='santjosep', defaults={'club_team_names': {'Infantil': 'SANT JOSEP'}})
    mock_fetch.return_value = [{"Nombre": "RESOLUCIONES 1", "URL": "disc.pdf", "Fecha": "10/11/2025"}]
    mock_download.return_value = (b'%PDF', 'sha')

    call_command('scrape_federation_circulars', season='2026-27', tipo=[6])

    assert FederationCircular.objects.get().rows_extracted_at is None
