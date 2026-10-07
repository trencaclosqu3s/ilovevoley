"""Sincroniza las noticias de la FVBIB (#370): metadatos y enlace, sin cuerpo HTML."""
from datetime import datetime

import requests

from ilovevoley.competitions.models import FederationNews
from ilovevoley.competitions.services.balearic_callups_client import DEFAULT_HEADERS

# Variante .dcl: la que usa la propia web; get_noticias.asp?tipo= puede devolver error SQL.
NEWS_URL = 'https://www.voleibolib.net/JSON/get_noticias.dcl'
PAGE_SIZE = 100


def _fetch_page(page, session):
    resp = session.get(NEWS_URL, params={'n': PAGE_SIZE, 'pag': page, 'tipo': ''}, headers=DEFAULT_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json().get('items', [])


def run_news_scrape(max_pages=5, session=None):
    """Devuelve ``{'created': n}``. Sin ``tipo`` el listado trae todas (playa incluida).

    Para al llegar a una página sin noticias nuevas: en régimen diario es una sola petición y
    la primera pasada rellena hasta ``max_pages`` × 100 noticias.
    """
    session = session or requests.Session()
    created = 0
    for page in range(max_pages):
        items = _fetch_page(page, session)
        new_in_page = 0
        for item in items:
            try:
                published_at = datetime.strptime((item.get('Fecha') or '').strip(), '%d/%m/%Y').date()
            except ValueError:
                published_at = None
            _, is_new = FederationNews.objects.update_or_create(
                federation_id=item['ID'],
                defaults={
                    'published_at': published_at,
                    'title': (item.get('Titular') or '').strip(),
                    'kind': (item.get('tipo') or '').strip(),
                    'image_name': (item.get('Imagen') or '').strip(),
                },
            )
            new_in_page += is_new
        created += new_in_page
        if len(items) < PAGE_SIZE or not new_in_page:
            break
    return {'created': created}
