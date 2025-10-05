from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from videosvoley.videos.models import League
from videosvoley.videos.scraping import FederationScraper
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Ejecuta scraping de una liga específica'

    def add_arguments(self, parser):
        parser.add_argument(
            '--league-id',
            type=str,
            required=True,
            help='ID de la federación de la liga a scrapear'
        )
        parser.add_argument(
            '--round',
            type=int,
            help='Jornada específica para endpoints que lo requieran'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Mostrar información detallada'
        )

    def handle(self, *args, **options):
        league_id = options['league_id']
        round_number = options.get('round', 1)
        verbose = options['verbose']

        if verbose:
            logging.basicConfig(level=logging.INFO)

        try:
            league = League.objects.get(federation_id=league_id, is_active=True)
        except League.DoesNotExist:
            raise CommandError(f'Liga con ID {league_id} no encontrada o inactiva')

        self.stdout.write(f'Iniciando scraping de liga: {league.name}')

        scraper = FederationScraper(league)
        
        try:
            results = scraper.scrape_all_endpoints(round=round_number)
            
            # Mostrar resumen de resultados
            for endpoint_type, data in results.items():
                if 'error' in data:
                    self.stdout.write(
                        self.style.ERROR(f'{endpoint_type}: Error - {data["error"]}')
                    )
                else:
                    teams_count = len(data.get('teams', []))
                    standings_count = len(data.get('standings', []))
                    matches_count = len(data.get('matches', []))
                    
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'{endpoint_type}: '
                            f'{teams_count} equipos, '
                            f'{standings_count} clasificaciones, '
                            f'{matches_count} partidos'
                        )
                    )

            self.stdout.write(
                self.style.SUCCESS(f'Scraping completado para {league.name}')
            )

        except Exception as e:
            logger.error(f'Error durante scraping: {e}')
            raise CommandError(f'Error durante scraping: {e}')