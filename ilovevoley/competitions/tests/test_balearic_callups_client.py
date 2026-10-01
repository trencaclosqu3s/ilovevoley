import pytest
from unittest.mock import patch, MagicMock
from ilovevoley.core.models import Season
from ilovevoley.competitions.services.balearic_callups_client import (
    fetch_balearic_circulares,
    download_callup_pdf,
    calculate_federation_temp,
)


@pytest.mark.django_db
@patch('requests.Session.get')
def test_fetch_balearic_circulares(mock_get):
    season = Season.objects.create(name='2025-26', start_year=2025, end_year=2026, is_current=True)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "items": [
            {"Nombre": "3ª CONVOCATORIA SELECCIO BALEAR VP INF MASC", "URL": "1785324870_3735.pdf", "Fecha": "29/07/2026"}
        ]
    }
    mock_get.return_value = mock_resp

    items = fetch_balearic_circulares(season)
    assert len(items) == 1
    assert items[0]['URL'] == '1785324870_3735.pdf'
    assert 'temp=2526' in mock_get.call_args[0][0]


@pytest.mark.django_db
@patch('requests.Session.get')
def test_fetch_balearic_circulares_temp_override(mock_get):
    season = Season.objects.create(name='2025-26', start_year=2025, end_year=2026, is_current=True)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"items": []}
    mock_get.return_value = mock_resp

    fetch_balearic_circulares(season, temp_override='2425')
    assert 'temp=2425' in mock_get.call_args[0][0]


@patch('requests.Session.get')
def test_download_callup_pdf(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'%PDF-1.4 dummy content'
    mock_get.return_value = mock_resp

    pdf_bytes, sha256 = download_callup_pdf('1785324870_3735.pdf')
    assert pdf_bytes == b'%PDF-1.4 dummy content'
    assert len(sha256) == 64
    assert '1785324870_3735.pdf' in mock_get.call_args[0][0]


def test_calculate_federation_temp():
    season = Season(name='2025-26', start_year=2025, end_year=2026)
    assert calculate_federation_temp(season) == '2526'

    season2 = Season(name='2024-25', start_year=2024, end_year=2025)
    assert calculate_federation_temp(season2) == '2425'
