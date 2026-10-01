import pytest
from unittest.mock import patch
from django.core.management import call_command
from ilovevoley.core.models import Season
from ilovevoley.competitions.models import FederationCallUp
from ilovevoley.competitions.tasks import scrape_balearic_callups_task


@pytest.mark.django_db
@patch('ilovevoley.competitions.services.balearic_callups_client.fetch_balearic_circulares')
@patch('ilovevoley.competitions.services.balearic_callups_client.download_callup_pdf')
@patch('ilovevoley.competitions.services.callup_parser.extract_callup_players_from_pdf')
def test_scrape_balearic_callups_command(mock_extract, mock_download, mock_fetch):
    season = Season.objects.create(name='2025-26', start_year=2025, end_year=2026, is_current=True)
    mock_fetch.return_value = [
        {"Nombre": "3ª CONVOCATORIA SELECCIO BALEAR VP INF MASC", "URL": "1785324870_3735.pdf", "Fecha": "29/07/2026"}
    ]
    mock_download.return_value = (b'%PDF-1.4 test', 'mocked_sha256')
    mock_extract.return_value = ("Raw text", [
        {'club': 'CV SANT JOSEP', 'last_name': 'RIERA', 'first_name': 'LLUC', 'birth_year': 2013}
    ])

    call_command('scrape_balearic_callups', season='2025-26', no_notify=True)
    assert FederationCallUp.objects.filter(source_url='1785324870_3735.pdf').exists()
    callup = FederationCallUp.objects.get(source_url='1785324870_3735.pdf')
    assert callup.players.count() == 1
    assert callup.modality == 'beach'
    assert callup.category_name == 'Infantil'
    assert callup.gender == 'M'
    assert callup.callup_number == '3ª'


@pytest.mark.django_db
@patch('ilovevoley.competitions.services.balearic_callups_client.fetch_balearic_circulares')
@patch('ilovevoley.competitions.services.balearic_callups_client.download_callup_pdf')
@patch('ilovevoley.competitions.services.callup_parser.extract_callup_players_from_pdf')
def test_scrape_balearic_callups_dry_run(mock_extract, mock_download, mock_fetch):
    season = Season.objects.create(name='2025-26', start_year=2025, end_year=2026, is_current=True)
    mock_fetch.return_value = [
        {"Nombre": "3ª CONVOCATORIA SELECCIO BALEAR VP INF MASC", "URL": "1785324870_3735.pdf", "Fecha": "29/07/2026"}
    ]
    mock_download.return_value = (b'%PDF-1.4 test', 'mocked_sha256')
    mock_extract.return_value = ("Raw text", [
        {'club': 'CV SANT JOSEP', 'last_name': 'RIERA', 'first_name': 'LLUC', 'birth_year': 2013}
    ])

    call_command('scrape_balearic_callups', season='2025-26', dry_run=True, no_notify=True)
    assert not FederationCallUp.objects.filter(source_url='1785324870_3735.pdf').exists()


@pytest.mark.django_db
@patch('ilovevoley.competitions.services.balearic_callups_client.fetch_balearic_circulares')
@patch('ilovevoley.competitions.services.balearic_callups_client.download_callup_pdf')
@patch('ilovevoley.competitions.services.callup_parser.extract_callup_players_from_pdf')
def test_scrape_balearic_callups_celery_task(mock_extract, mock_download, mock_fetch):
    season = Season.objects.create(name='2025-26', start_year=2025, end_year=2026, is_current=True)
    mock_fetch.return_value = [
        {"Nombre": "3ª CONVOCATORIA SELECCIO BALEAR VP INF MASC", "URL": "1785324870_3735.pdf", "Fecha": "29/07/2026"}
    ]
    mock_download.return_value = (b'%PDF-1.4 test', 'mocked_sha256')
    mock_extract.return_value = ("Raw text", [
        {'club': 'CV SANT JOSEP', 'last_name': 'RIERA', 'first_name': 'LLUC', 'birth_year': 2013}
    ])

    result = scrape_balearic_callups_task(season_id=season.id, no_notify=True)
    assert result['processed'] == 1
    assert FederationCallUp.objects.filter(source_url='1785324870_3735.pdf').exists()
