import pytest
from unittest.mock import patch
from django.core.management import call_command
from ilovevoley.core.models import Season
from ilovevoley.competitions.models import FederationCallUp


@pytest.mark.django_db
@patch('ilovevoley.competitions.services.balearic_callups_client.fetch_balearic_circulares')
@patch('ilovevoley.competitions.services.balearic_callups_client.download_callup_pdf')
@patch('ilovevoley.competitions.services.callup_parser.extract_callup_players_from_pdf')
def test_scrape_balearic_tracking_command(mock_extract, mock_download, mock_fetch):
    season = Season.objects.create(name='2026-27', start_year=2026, end_year=2027, is_current=True)
    mock_fetch.return_value = [
        {"Nombre": "1ª SEGUIMENT FEDERATIU CAD FEM TEMP.26/27", "URL": "1790768090_9485.pdf", "Fecha": "30/09/2026"}
    ]
    mock_download.return_value = (b'%PDF-1.4 test', 'mocked_sha256')
    mock_extract.return_value = ("Raw text", [
        {'club': 'Algaida VC', 'last_name': 'Fuster', 'first_name': 'Emma', 'birth_year': 2013}
    ])

    call_command('scrape_balearic_tracking', season='2026-27', no_notify=True)

    assert mock_fetch.call_args.kwargs.get('tipo') == 22
    callup = FederationCallUp.objects.get(source_url='1790768090_9485.pdf')
    assert callup.callup_type == 'follow_up'
    assert callup.category_name == 'Cadete'
    assert callup.gender == 'F'
    assert callup.players.count() == 1


@pytest.mark.django_db
@patch('ilovevoley.competitions.services.balearic_callups_client.fetch_balearic_circulares')
@patch('ilovevoley.competitions.services.balearic_callups_client.download_callup_pdf')
@patch('ilovevoley.competitions.services.callup_parser.extract_callup_players_from_pdf')
def test_scrape_balearic_tracking_defaults_to_follow_up(mock_extract, mock_download, mock_fetch):
    """Un circular de tipo=22 cuyo título no lleva palabra clave no debe etiquetarse
    como selección: el endpoint manda y cae a seguimiento federativo."""
    Season.objects.create(name='2026-27', start_year=2026, end_year=2027, is_current=True)
    mock_fetch.return_value = [
        {"Nombre": "1ª CONVOCATORIA CAD FEM TEMP.26/27", "URL": "sin-clave.pdf", "Fecha": "30/09/2026"}
    ]
    mock_download.return_value = (b'%PDF-1.4 test', 'mocked_sha256')
    mock_extract.return_value = ("Raw text", [])

    call_command('scrape_balearic_tracking', season='2026-27', no_notify=True)

    callup = FederationCallUp.objects.get(source_url='sin-clave.pdf')
    assert callup.callup_type == 'follow_up'
