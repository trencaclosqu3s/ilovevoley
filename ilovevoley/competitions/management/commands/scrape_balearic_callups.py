from datetime import datetime
import logging
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from ilovevoley.core.models import Season
from ilovevoley.competitions.models import FederationCallUp, CallUpPlayer
from ilovevoley.competitions.services.balearic_callups_client import (
    fetch_balearic_circulares,
    download_callup_pdf,
)
from ilovevoley.competitions.services.callup_parser import (
    parse_callup_title,
    extract_callup_players_from_pdf,
)
from ilovevoley.competitions.services.callup_matcher import match_callup_player
from ilovevoley.competitions.services.notifications import (
    notify_callup_confirmed,
    notify_callup_suspected,
)

logger = logging.getLogger(__name__)


def run_balearic_callups_scrape(
    season=None,
    temp=None,
    dry_run=False,
    force=False,
    no_notify=False,
    stdout=None,
) -> dict:
    """
    Función orquestadora compartida entre el comando de gestión y la tarea Celery.
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

    out(f"Iniciando scrape de convocatorias para la temporada {season.name} (temp={temp or 'auto'})...")

    circulares = fetch_balearic_circulares(season, temp_override=temp)
    out(f"Obtenidas {len(circulares)} circulares de tipo 7.")

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
            pdf_bytes, sha256 = download_callup_pdf(url)
        except Exception as e:
            logger.warning(f"Error descargando PDF {url}: {e}")
            out(f"Error descargando PDF {url}: {e}")
            continue

        if existing_callup and existing_callup.pdf_sha256 == sha256 and not force:
            out(f"PDF sin cambios (SHA256 coincide): {url}")
            continue

        # Normalizar título y extraer jugadores
        title_meta = parse_callup_title(title)
        raw_text, players_data = extract_callup_players_from_pdf(pdf_bytes)

        out(f"  -> Convocatoria: {title_meta['callup_number'] or '-'} | {title_meta['category_name']} | {title_meta['gender']} | {title_meta['modality']}")
        out(f"  -> Extraídos {len(players_data)} jugadores del PDF.")

        if dry_run:
            out(f"  [DRY-RUN] No se persiste en BD ni se envían notificaciones.")
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
        callup.raw_text = raw_text

        filename = url.split('/')[-1]
        callup.pdf_file.save(filename, ContentFile(pdf_bytes), save=False)
        callup.save()

        # Procesar y cruzar cada jugador
        for p in players_data:
            match_res = match_callup_player(p, season)
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
                    notify_callup_confirmed(player_obj)
                elif player_obj.match_status == CallUpPlayer.STATUS_SUSPECTED:
                    notify_callup_suspected(player_obj)

        processed_count += 1

    return {
        'processed': processed_count,
        'players_count': new_players_count,
    }


class Command(BaseCommand):
    help = "Descarga y procesa convocatorias federativas de la selección balear (FVBIB)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--season',
            type=str,
            help="Nombre de la temporada (ej: '2025-26'). Por defecto la activa.",
        )
        parser.add_argument(
            '--temp',
            type=str,
            help="Parámetro de temporada para la API de voleibolib (ej: '2526').",
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Simula la descarga y parseo sin modificar la base de datos.",
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help="Fuerza el reprocesamiento aunque el PDF ya haya sido descargado.",
        )
        parser.add_argument(
            '--no-notify',
            action='store_true',
            help="Omite el envío de notificaciones Web Push.",
        )

    def handle(self, *args, **options):
        result = run_balearic_callups_scrape(
            season=options.get('season'),
            temp=options.get('temp'),
            dry_run=options.get('dry_run', False),
            force=options.get('force', False),
            no_notify=options.get('no_notify', False),
            stdout=self.stdout,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Scraping completado. Convocatorias procesadas: {result['processed']}, jugadores: {result['players_count']}."
            )
        )
