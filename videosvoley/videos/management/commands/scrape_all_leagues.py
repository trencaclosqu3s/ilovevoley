from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from videosvoley.videos.models import League
from videosvoley.videos.scraping import FederationScraper
import logging
import time

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Ejecuta scraping de todas las ligas activas'

    def add_arguments(self, parser):
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
        parser.add_argument(
            '--delay',
            type=float,
            default=2.0,
            help='Tiempo de espera entre ligas en segundos (default: 2.0)'
        )
        parser.add_argument(
            '--category',
            type=str,
            help='Filtrar solo ligas de una categoría específica'
        )

    def handle(self, *args, **options):
        round_number = options.get('round', 1)
        verbose = options['verbose']
        delay = options['delay']
        category_filter = options.get('category')

        if verbose:
            logging.basicConfig(level=logging.INFO)

        # Obtener ligas activas
        leagues = League.objects.filter(is_active=True).select_related('category')
        
        # Filtrar por categoría si se especifica
        if category_filter:
            leagues = leagues.filter(category__name__icontains=category_filter)

        if not leagues.exists():
            filter_msg = f" de categoría '{category_filter}'" if category_filter else ""
            raise CommandError(f'No se encontraron ligas activas{filter_msg}')

        self.stdout.write(f'Iniciando scraping de {leagues.count()} ligas activas...')

        total_results = {
            'success': 0,
            'errors': 0,
            'total_teams': 0,
            'total_matches': 0,
            'total_standings': 0
        }

        for i, league in enumerate(leagues):
            category_name = league.category.name if league.category else 'Sin categoría'
            self.stdout.write(f'\n[{i+1}/{leagues.count()}] {league.name} ({category_name})')
            
            try:
                scraper = FederationScraper(league)
                results = scraper.scrape_all_endpoints(round=round_number)
                
                # Procesar resultados
                league_success = True
                league_stats = {'teams': 0, 'matches': 0, 'standings': 0}
                
                for endpoint_type, data in results.items():
                    if 'error' in data:
                        self.stdout.write(
                            self.style.ERROR(f'  {endpoint_type}: Error - {data["error"]}')
                        )
                        league_success = False
                    else:
                        teams_count = len(data.get('teams', []))
                        standings_count = len(data.get('standings', []))
                        matches_count = len(data.get('matches', []))
                        
                        league_stats['teams'] += teams_count
                        league_stats['matches'] += matches_count
                        league_stats['standings'] += standings_count
                        
                        if verbose:
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f'  {endpoint_type}: '
                                    f'{teams_count} equipos, '
                                    f'{standings_count} clasificaciones, '
                                    f'{matches_count} partidos'
                                )
                            )

                # Actualizar estadísticas totales
                if league_success:
                    total_results['success'] += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'  ✓ Completado: {league_stats["teams"]} equipos, '
                            f'{league_stats["matches"]} partidos, '
                            f'{league_stats["standings"]} clasificaciones'
                        )
                    )
                else:
                    total_results['errors'] += 1
                    self.stdout.write(
                        self.style.ERROR(f'  ✗ Errores en algunos endpoints')
                    )
                
                total_results['total_teams'] += league_stats['teams']
                total_results['total_matches'] += league_stats['matches']
                total_results['total_standings'] += league_stats['standings']

                # Rate limiting entre ligas
                if i < leagues.count() - 1:  # No esperar después de la última liga
                    if verbose:
                        self.stdout.write(f'  Esperando {delay}s antes de la siguiente liga...')
                    time.sleep(delay)

            except Exception as e:
                total_results['errors'] += 1
                logger.error(f'Error durante scraping de {league.name}: {e}')
                self.stdout.write(
                    self.style.ERROR(f'  ✗ Error crítico: {e}')
                )

        # Resumen final
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('RESUMEN FINAL'))
        self.stdout.write(f'Ligas procesadas: {total_results["success"] + total_results["errors"]}')
        self.stdout.write(self.style.SUCCESS(f'Exitosas: {total_results["success"]}'))
        if total_results['errors'] > 0:
            self.stdout.write(self.style.ERROR(f'Con errores: {total_results["errors"]}'))
        
        self.stdout.write(f'\nDatos obtenidos:')
        self.stdout.write(f'  - Equipos: {total_results["total_teams"]}')
        self.stdout.write(f'  - Partidos: {total_results["total_matches"]}')
        self.stdout.write(f'  - Clasificaciones: {total_results["total_standings"]}')
        
        if total_results['errors'] == 0:
            self.stdout.write(self.style.SUCCESS('\n¡Scraping completado exitosamente!'))
        else:
            self.stdout.write(self.style.WARNING('\nScraping completado con algunos errores.'))