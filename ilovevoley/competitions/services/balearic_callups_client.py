import hashlib
from typing import Any
import requests
from ilovevoley.core.models import Season

BASE_CIRCULARES_URL = 'https://www.voleibolib.net/JSON/get_circulares.asp'
BASE_PDF_DOWNLOAD_URL = 'https://voleibolib.federatio.com/upload/descargas/'
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
}


def calculate_federation_temp(season: Season) -> str:
    """
    Calcula el parámetro 'temp' para la API de voleibolib a partir de Season.
    Formato: YY(YY+1), ej: 2025-26 -> '2526'.
    """
    if season.start_year and season.end_year:
        return f"{season.start_year % 100:02d}{season.end_year % 100:02d}"
    # Fallback parseando el nombre si start/end year no están fijados
    name = (season.name or '').strip()
    parts = name.split('-')
    if len(parts) == 2:
        try:
            y1 = int(parts[0]) % 100
            y2 = int(parts[1]) % 100
            return f"{y1:02d}{y2:02d}"
        except ValueError:
            pass
    return '2526'


def fetch_balearic_circulares(
    season: Season,
    temp_override: str | None = None,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """
    Consulta las circulares de tipo 7 (convocatorias) para la temporada dada en la API de FVBIB.
    """
    temp = temp_override or calculate_federation_temp(season)
    url = f"{BASE_CIRCULARES_URL}?tipo=7&pag=0&temp={temp}"

    s = session or requests.Session()
    resp = s.get(url, headers=DEFAULT_HEADERS, timeout=15)
    resp.raise_for_status()

    data = resp.json()
    if isinstance(data, dict):
        return data.get('items', [])
    if isinstance(data, list):
        return data
    return []


def download_callup_pdf(
    pdf_filename_or_url: str,
    session: requests.Session | None = None,
) -> tuple[bytes, str]:
    """
    Descarga el fichero PDF de la convocatoria y calcula su hash SHA-256.
    Retorna: (pdf_bytes, sha256_hex)
    """
    url = pdf_filename_or_url
    if not url.startswith('http://') and not url.startswith('https://'):
        clean_name = url.lstrip('/')
        url = f"{BASE_PDF_DOWNLOAD_URL}{clean_name}"

    s = session or requests.Session()
    resp = s.get(url, headers=DEFAULT_HEADERS, timeout=30)
    resp.raise_for_status()

    content = resp.content
    sha256 = hashlib.sha256(content).hexdigest()
    return content, sha256
