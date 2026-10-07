"""Indexa circulares federativas (FVBIB) de cualquier tipo: metadatos y enlace al PDF.

En las disciplinarias (tipo 6) se lee además el PDF y solo se guardan las filas que
mencionan a un equipo de un tenant (``FederationSanction``); el resto se descarta.
"""
import io
import logging
import re
import unicodedata
from datetime import datetime

import pypdf
from django.utils import timezone

from ilovevoley.core.models import Category, Organization
from ilovevoley.competitions.models import FederationCircular, FederationSanction
from ilovevoley.competitions.services import balearic_callups_client

logger = logging.getLogger(__name__)

# Sanciones y normas (#368) más vóley playa (#372, de momento solo visible en el admin).
DEFAULT_TIPOS = (
    FederationCircular.TIPO_DISCIPLINARY,
    FederationCircular.TIPO_RULES,
    FederationCircular.TIPO_BEACH,
)

_ROW_START = re.compile(r'(?=\b\d{1,2}/\d{1,2}/\d{2}\b)')


def run_circulars_scrape(season, tipos=DEFAULT_TIPOS, temp=None, dry_run=False):
    """Devuelve ``{'created': n, 'existing': n, 'sanctions': n}``; con ``dry_run`` no escribe en BD."""
    created = existing = 0
    for tipo in tipos:
        for circ in balearic_callups_client.fetch_balearic_circulares(season, tipo=tipo, temp_override=temp):
            title = (circ.get('Nombre') or '').strip()
            if not title:
                continue
            file_name = (circ.get('URL') or '').strip()
            try:
                circular_date = datetime.strptime((circ.get('Fecha') or '').strip(), '%d/%m/%Y').date()
            except ValueError:
                circular_date = None
            lookup = {'tipo': tipo, 'title': title, 'circular_date': circular_date}
            if dry_run:
                is_new = not FederationCircular.objects.filter(**lookup).exists()
            else:
                circular, is_new = FederationCircular.objects.get_or_create(
                    **lookup, defaults={'season': season, 'file_name': file_name},
                )
                if not is_new and file_name and circular.file_name != file_name:
                    # La federación publica el PDF (o lo sustituye) después de la circular.
                    circular.file_name = file_name
                    circular.rows_extracted_at = None
                    circular.save(update_fields=['file_name', 'rows_extracted_at'])
            created += is_new
            existing += not is_new
    sanctions = 0 if dry_run else extract_pending_sanctions(season)
    return {'created': created, 'existing': existing, 'sanctions': sanctions}


def extract_pending_sanctions(season):
    """Lee los PDF disciplinarios aún sin procesar y guarda las filas de los tenants."""
    pending = FederationCircular.objects.filter(
        season=season,
        tipo=FederationCircular.TIPO_DISCIPLINARY,
        rows_extracted_at__isnull=True,
    ).exclude(file_name='')
    tenants = [(org, _tenant_needles(org)) for org in Organization.objects.all()]
    tenants = [(org, needles) for org, needles in tenants if needles]
    categories = [(cat, _normalize(cat.name)) for cat in Category.objects.filter(is_active=True)]

    saved = 0
    for circular in pending:
        try:
            pdf_bytes, _sha = balearic_callups_client.download_callup_pdf(circular.file_name)
            text = _pdf_text(pdf_bytes)
        except Exception as e:
            # Se reintenta en la siguiente pasada: rows_extracted_at sigue vacío.
            logger.warning(f"No se pudo leer la circular disciplinaria {circular.file_name}: {e}")
            continue
        for index, row in enumerate(_split_rows(text)):
            normalized = _normalize(row)
            category = _match_category(normalized, categories)
            for org, needles in tenants:
                if any(needle in normalized for needle in needles):
                    _, is_new = FederationSanction.objects.get_or_create(
                        circular=circular,
                        organization=org,
                        row_index=index,
                        defaults={'text': row, 'category': category, 'sanction_date': _row_date(row)},
                    )
                    saved += is_new
        circular.rows_extracted_at = timezone.now()
        circular.save(update_fields=['rows_extracted_at'])
    return saved


def _pdf_text(pdf_bytes):
    return '\n'.join(page.extract_text() or '' for page in pypdf.PdfReader(io.BytesIO(pdf_bytes)).pages)


def _clean(text):
    # Quita caracteres de formato (p. ej. U+200B, frecuentes en estos PDF) y unifica espacios.
    return re.sub(r'\s+', ' ', ''.join(c for c in text if unicodedata.category(c) != 'Cf')).strip()


def _normalize(text):
    stripped = unicodedata.normalize('NFKD', _clean(text))
    return ''.join(c for c in stripped if not unicodedata.combining(c)).casefold()


def _split_rows(text):
    """Una fila por cada fecha dd/mm/aa; lo anterior a la primera es la cabecera y se descarta."""
    parts = _ROW_START.split(_clean(text))[1:]
    # El pie ("Federación de Voleibol… Comité de Competición…") se queda pegado a la última fila.
    return [re.split(r'\s*Federación de Voleibol', p, maxsplit=1)[0].strip() for p in parts]


def _row_date(row):
    day, month, year = row.split(' ', 1)[0].split('/')
    try:
        return datetime(2000 + int(year), int(month), int(day)).date()
    except ValueError:
        return None


def _tenant_needles(org):
    return [n for n in (_normalize(v) for v in (org.club_team_names or {}).values() if v) if n]


def _match_category(normalized_row, categories):
    matches = [(len(name), cat) for cat, name in categories if name and name in normalized_row]
    return max(matches, key=lambda m: m[0])[1] if matches else None
