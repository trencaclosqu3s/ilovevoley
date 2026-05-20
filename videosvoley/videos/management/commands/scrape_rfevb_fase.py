import logging

from django.core.management.base import BaseCommand

from videosvoley.videos.rfevb_service import scrape_rfevb_fases

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Scraping de fases de campeonatos nacionales RFEVB'

    def add_arguments(self, parser):
        parser.add_argument('--competition-id', required=True, type=int,
                            dest='competition_id')
        parser.add_argument('--fase-ids', required=True, type=str,
                            dest='fase_ids',
                            help='IDs de fase separados por coma, ej: 2193,2194')
        parser.add_argument('--parent-league', required=True, type=str,
                            dest='parent_league',
                            help='federation_id de la liga padre, ej: ceim_2526')
        parser.add_argument('--dry-run', action='store_true', dest='dry_run')
        parser.add_argument('--delay', type=float, default=2.0, dest='delay')

    def handle(self, *args, **options):
        fase_ids = [int(x.strip()) for x in options['fase_ids'].split(',')]

        if options['dry_run']:
            self.stdout.write('[DRY RUN] No se guardarán cambios')

        result = scrape_rfevb_fases(
            competition_id=options['competition_id'],
            fase_ids=fase_ids,
            parent_league_id=options['parent_league'],
            dry_run=options['dry_run'],
            delay=options['delay'],
        )

        if 'error' in result:
            self.stderr.write(self.style.ERROR(result['error']))
            return

        self.stdout.write(self.style.SUCCESS(
            f"\nRESUMEN: {len(fase_ids)} fases | "
            f"{result['matches_found']} partidos | "
            f"{result.get('created', 0)} creados | "
            f"{result.get('updated', 0)} actualizados | "
            f"{result.get('skipped', 0)} omitidos | "
            f"{len(result['errors'])} errores"
        ))
