import pytest
from unittest.mock import patch
from django.core.management import call_command

from ilovevoley.core.models import Season
from ilovevoley.competitions.models import FederationCircular

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
    assert [c.kwargs['tipo'] for c in mock_fetch.call_args_list] == [6, 11]
