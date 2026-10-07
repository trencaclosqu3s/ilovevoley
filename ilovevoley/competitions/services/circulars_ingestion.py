"""Indexa circulares federativas (FVBIB) de cualquier tipo: solo metadatos y enlace al PDF."""
from datetime import datetime

from ilovevoley.competitions.models import FederationCircular
from ilovevoley.competitions.services import balearic_callups_client

# Prioridad de #368: sanciones y normas. El resto de tipos se piden con --tipo.
DEFAULT_TIPOS = (FederationCircular.TIPO_DISCIPLINARY, FederationCircular.TIPO_RULES)


def run_circulars_scrape(season, tipos=DEFAULT_TIPOS, temp=None, dry_run=False):
    """Devuelve ``{'created': n, 'existing': n}``; con ``dry_run`` no escribe en BD."""
    created = existing = 0
    for tipo in tipos:
        for circ in balearic_callups_client.fetch_balearic_circulares(season, tipo=tipo, temp_override=temp):
            title = (circ.get('Nombre') or '').strip()
            if not title:
                continue
            try:
                circular_date = datetime.strptime((circ.get('Fecha') or '').strip(), '%d/%m/%Y').date()
            except ValueError:
                circular_date = None
            lookup = {'tipo': tipo, 'title': title, 'circular_date': circular_date}
            if dry_run:
                is_new = not FederationCircular.objects.filter(**lookup).exists()
            else:
                _, is_new = FederationCircular.objects.get_or_create(
                    **lookup,
                    defaults={'season': season, 'file_name': (circ.get('URL') or '').strip()},
                )
            created += is_new
            existing += not is_new
    return {'created': created, 'existing': existing}
