from django.core.management.base import BaseCommand

from ilovevoley.competitions.services.callup_ingestion import run_callups_scrape


def run_balearic_tracking_scrape(
    season=None,
    temp=None,
    dry_run=False,
    force=False,
    no_notify=False,
    stdout=None,
) -> dict:
    """Ingesta de circulares de tecnificación y seguimiento federativo (#288, tipo=22)."""
    return run_callups_scrape(
        season=season,
        tipo=22,
        temp=temp,
        dry_run=dry_run,
        force=force,
        no_notify=no_notify,
        stdout=stdout,
    )


class Command(BaseCommand):
    help = "Descarga y procesa circulares de tecnificación y seguimiento federativo (FVBIB)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--season',
            type=str,
            help="Nombre de la temporada (ej: '2026-27'). Por defecto la activa.",
        )
        parser.add_argument(
            '--temp',
            type=str,
            help="Parámetro de temporada para la API de voleibolib (ej: '2627').",
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
        result = run_balearic_tracking_scrape(
            season=options.get('season'),
            temp=options.get('temp'),
            dry_run=options.get('dry_run', False),
            force=options.get('force', False),
            no_notify=options.get('no_notify', False),
            stdout=self.stdout,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Scraping completado. Circulares procesadas: {result['processed']}, jugadores: {result['players_count']}."
            )
        )
