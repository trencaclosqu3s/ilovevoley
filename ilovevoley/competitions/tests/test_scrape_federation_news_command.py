import pytest
from unittest.mock import patch
from django.core.management import call_command

from ilovevoley.competitions.models import FederationNews

PAGE = [
    {"ID": 18520, "Fecha": "02/10/2026", "Titular": " El vòlei balear comença ", "tipo": "Generales", "Imagen": "a.jpg"},
    {"ID": 14191, "Fecha": "sin-fecha", "Titular": "Sin tipo ni imagen", "tipo": None, "Imagen": None},
]


@pytest.mark.django_db
@patch('ilovevoley.competitions.services.news_ingestion._fetch_page', return_value=PAGE)
def test_scrape_news_is_idempotent_and_tolerates_missing_fields(mock_fetch):
    """Segunda pasada no duplica ni sigue paginando; tipo, imagen o fecha nulos se toleran."""
    call_command('scrape_federation_news')
    call_command('scrape_federation_news')

    assert FederationNews.objects.count() == 2
    assert mock_fetch.call_count == 2  # una página por pasada: sin novedades no pide más
    news = FederationNews.objects.get(federation_id=14191)
    assert (news.published_at, news.kind, news.image_url) == (None, '', '')
    assert FederationNews.objects.get(federation_id=18520).title == 'El vòlei balear comença'
