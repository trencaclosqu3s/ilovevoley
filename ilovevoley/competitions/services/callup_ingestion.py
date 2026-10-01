"""Orquestador unificado de ingesta de circulares federativas (FVBIB).

Un único flujo parametrizado por ``tipo`` de circular sirve tanto a las
convocatorias de la selección balear (#287, ``tipo=7``) como a las de
tecnificación y seguimiento federativo (#288, ``tipo=22``): descarga del JSON,
descarga del PDF, parseo de título y jugadores, cruce con las plantillas del
tenant y notificación push.
"""
from datetime import datetime
import logging

from django.core.files.base import ContentFile
from django.core.management.base import CommandError

from ilovevoley.core.models import Season
from ilovevoley.competitions.models import FederationCallUp, CallUpPlayer
from ilovevoley.competitions.services import (
    balearic_callups_client,
    callup_matcher,
    callup_parser,
    notifications,
)

logger = logging.getLogger(__name__)

# Tipo por defecto de cada endpoint: el título solo lo afina cuando indica un evento
# distinto (tecnificación, seguimiento o supervisión).
DEFAULT_TYPE_BY_TIPO = {
    7: FederationCallUp.TYPE_SELECTION,
    22: FederationCallUp.TYPE_FOLLOW_UP,
}


def run_callups_scrape(
    season=None,
    tipo: int = 7,
    temp: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    no_notify: bool = False,
    stdout=None,
) -> dict:
    """
    Función orquestadora compartida por los comandos de gestión y las tareas Celery.

    ``tipo`` es el parámetro de la API de voleibolib (7 selección, 22 tecnificación y
    seguimiento). El tipo de cada circular se infiere del título (``event_type``).
    """
    out = stdout.write if stdout else (lambda msg: None)

    if season is None:
        season = Season.objects.current()
        if not season:
            raise CommandError("No hay una temporada actual configurada y no se especificó --season.")
    elif isinstance(season, str):
        try:
            season = Season.objects.get(name=season)
        except Season.DoesNotExist:
            raise CommandError(f"No existe la temporada '{season}'.")

    out(f"Iniciando scrape de circulares tipo {tipo} para la temporada {season.name} (temp={temp or 'auto'})...")

    circulares = balearic_callups_client.fetch_balearic_circulares(season, tipo=tipo, temp_override=temp)
    out(f"Obtenidas {len(circulares)} circulares de tipo {tipo}.")

    processed_count = 0
    new_players_count = 0

    for circ in circulares:
        title = (circ.get('Nombre') or '').strip()
        url = (circ.get('URL') or '').strip()
        fecha_str = (circ.get('Fecha') or '').strip()

        if not url:
            continue

        circular_date = None
        if fecha_str:
            try:
                circular_date = datetime.strptime(fecha_str, '%d/%m/%Y').date()
            except ValueError:
                pass

        existing_callup = FederationCallUp.objects.filter(source_url=url).first()
        if existing_callup and not force:
            out(f"Saltando circular ya existente: {title} ({url})")
            continue

        out(f"Descargando PDF: {url} ({title})...")
        try:
            pdf_bytes, sha256 = balearic_callups_client.download_callup_pdf(url)
        except Exception as e:
            logger.warning(f"Error descargando PDF {url}: {e}")
            out(f"Error descargando PDF {url}: {e}")
            continue

        if existing_callup and existing_callup.pdf_sha256 == sha256 and not force:
            out(f"PDF sin cambios (SHA256 coincide): {url}")
            continue

        # Normalizar título y extraer jugadores
        title_meta = callup_parser.parse_callup_title(title)
        raw_text, players_data = callup_parser.extract_callup_players_from_pdf(pdf_bytes)
        detected_type = title_meta.get('event_type')
        if detected_type in (
            FederationCallUp.TYPE_TRAINING,
            FederationCallUp.TYPE_FOLLOW_UP,
            FederationCallUp.TYPE_SUPERVISION,
        ):
            callup_type = detected_type
        else:
            callup_type = DEFAULT_TYPE_BY_TIPO.get(tipo, FederationCallUp.TYPE_SELECTION)

        out(f"  -> Circular: {title_meta['callup_number'] or '-'} | {callup_type} | {title_meta['category_name']} | {title_meta['gender']} | {title_meta['modality']}")
        out(f"  -> Extraídos {len(players_data)} jugadores del PDF.")

        if dry_run:
            out("  [DRY-RUN] No se persiste en BD ni se envían notificaciones.")
            processed_count += 1
            new_players_count += len(players_data)
            continue

        # Persistir o actualizar FederationCallUp
        callup = existing_callup or FederationCallUp(source_url=url)
        callup.season = season
        callup.title = title
        callup.circular_date = circular_date
        callup.pdf_sha256 = sha256
        callup.modality = title_meta['modality']
        callup.category_name = title_meta['category_name']
        callup.gender = title_meta['gender']
        callup.callup_number = title_meta['callup_number']
        callup.callup_type = callup_type
        callup.raw_text = raw_text

        filename = url.split('/')[-1]
        callup.pdf_file.save(filename, ContentFile(pdf_bytes), save=False)
        callup.save()

        if existing_callup and force:
            callup.players.all().delete()

        # Procesar y cruzar cada jugador
        for p in players_data:
            match_res = callup_matcher.match_callup_player(p, season, callup=callup)
            player_obj, _ = CallUpPlayer.objects.get_or_create(
                callup=callup,
                raw_first_name=p['first_name'],
                raw_last_name=p['last_name'],
                raw_club=p['club'],
                defaults={
                    'raw_birth_year': p.get('birth_year'),
                    'organization': match_res.get('organization'),
                    'person': match_res.get('person'),
                    'match_status': match_res.get('match_status', 'unmatched'),
                    'match_score': match_res.get('match_score', 0.0),
                    'match_notes': match_res.get('match_notes', ''),
                },
            )
            # Si ya existía, actualizar cruce
            if not _:
                player_obj.raw_birth_year = p.get('birth_year')
                player_obj.organization = match_res.get('organization')
                player_obj.person = match_res.get('person')
                player_obj.match_status = match_res.get('match_status', 'unmatched')
                player_obj.match_score = match_res.get('match_score', 0.0)
                player_obj.match_notes = match_res.get('match_notes', '')
                player_obj.save()

            new_players_count += 1

            if not no_notify:
                if player_obj.match_status == CallUpPlayer.STATUS_CONFIRMED:
                    notifications.notify_callup_confirmed(player_obj)
                elif player_obj.match_status == CallUpPlayer.STATUS_SUSPECTED:
                    notifications.notify_callup_suspected(player_obj)

        processed_count += 1

    return {
        'processed': processed_count,
        'players_count': new_players_count,
    }
