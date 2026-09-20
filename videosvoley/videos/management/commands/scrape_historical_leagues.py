from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from videosvoley.core.models import Season
from videosvoley.videos.models import League, Category, ScrapingEndpoint
from videosvoley.videos.scraping import FederationScraper
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Scraping de ligas históricas y externas para análisis estadístico'

    def add_arguments(self, parser):
        parser.add_argument(
            '--league-id',
            type=str,
            help='ID de la liga específica a procesar'
        )
        parser.add_argument(
            '--season',
            type=str,
            help='Temporada específica (ej: 2023-24)'
        )
        parser.add_argument(
            '--visibility-type',
            type=str,
            choices=['historical', 'external', 'reference'],
            default='historical',
            help='Tipo de visibilidad para las ligas creadas'
        )
        parser.add_argument(
            '--federation-id',
            type=str,
            help='ID de federación para ligas externas'
        )
        parser.add_argument(
            '--league-name',
            type=str,
            help='Nombre de la liga'
        )
        parser.add_argument(
            '--category',
            type=str,
            help='Categoría de la liga'
        )
        parser.add_argument(
            '--base-url',
            type=str,
            default='https://www.voleibolib.net',
            help='URL base para el scraping'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Ejecutar sin hacer cambios reales'
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
            help='Delay entre requests (segundos)'
        )
        parser.add_argument(
            '--match-format',
            type=str,
            choices=['standard', 'alevin_balear', 'tournament_3sets', 'custom'],
            help='Formato de partido para la liga (auto-detectado por categoría si no se especifica)'
        )

    def handle(self, *args, **options):
        self.verbosity = options['verbose']
        self.dry_run = options['dry_run']
        self.delay = options['delay']
        
        if self.verbosity:
            logger.setLevel(logging.INFO)
        
        try:
            if options['league_id']:
                self.scrape_specific_league(options)
            else:
                self.scrape_multiple_leagues(options)
                
        except Exception as e:
            logger.error(f"Error durante el scraping: {e}")
            raise CommandError(f"Error durante el scraping: {e}")

    def get_match_format_for_category(self, category_name, explicit_format=None):
        """Determina el formato de partido basado en la categoría"""
        if explicit_format:
            return explicit_format
        
        # Auto-detección basada en categoría
        if category_name:
            category_lower = category_name.lower()
            if 'alevin' in category_lower:
                return 'alevin_balear'
            elif any(keyword in category_lower for keyword in ['torneo', 'tournament', 'copa']):
                return 'tournament_3sets'
        
        return 'standard'

    def scrape_specific_league(self, options):
        """Scraping de una liga específica"""
        league_id = options['league_id']
        season = options['season'] or '2024-25'
        season_obj = Season.objects.resolve(season)
        visibility_type = options['visibility_type']
        
        self.stdout.write(f"Procesando liga específica: {league_id}")
        
        # Crear o obtener la liga
        league_data = {
            'federation_id': league_id,
            'season': season_obj,
            'visibility_type': visibility_type,
            'is_historical': visibility_type == 'historical',
            'is_our_team_related': visibility_type != 'external',
            'base_url': options['base_url']
        }
        
        if options['league_name']:
            league_data['name'] = options['league_name']
        else:
            league_data['name'] = f"Liga {league_id} ({season})"
        
        category_obj = None
        if options['category']:
            try:
                category_obj = Category.objects.get(name=options['category'])
                league_data['category'] = category_obj
            except Category.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f"Categoría '{options['category']}' no encontrada")
                )
        
        # Determinar formato de partido
        match_format = self.get_match_format_for_category(
            options.get('category'), 
            options.get('match_format')
        )
        league_data['match_format'] = match_format
        
        if self.verbosity:
            self.stdout.write(f"Formato de partido asignado: {match_format}")
        
        if not self.dry_run:
            league, created = League.objects.get_or_create(
                federation_id=league_id,
                season=season_obj,
                defaults=league_data
            )
            
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"Liga creada: {league.name}")
                )
            else:
                # Actualizar campos existentes
                for key, value in league_data.items():
                    setattr(league, key, value)
                league.save()
                self.stdout.write(
                    self.style.SUCCESS(f"Liga actualizada: {league.name}")
                )
            
            # Configurar endpoints automáticamente
            self.setup_endpoints(league)
        else:
            self.stdout.write(f"[DRY RUN] Se crearía/actualizaría liga: {league_data['name']}")
        
        # Realizar scraping
        if not self.dry_run:
            self.perform_scraping(league, options)

    def setup_endpoints(self, league):
        """Configura endpoints básicos para la liga"""
        endpoints_config = [
            {
                'endpoint_type': 'standings',
                'url_pattern': 'JSON/get_clasificacion.asp?id={league_id}',
                'parser_type': 'table_standings'
            },
            {
                'endpoint_type': 'results',
                'url_pattern': 'JSON/get_resultados.asp?id={league_id}&jor={round}',
                'parser_type': 'match_results'
            },
            {
                'endpoint_type': 'calendar',
                'url_pattern': 'JSON/get_calendario.asp?id={league_id}',
                'parser_type': 'match_calendar'
            }
        ]

        for endpoint_config in endpoints_config:
            endpoint, created = ScrapingEndpoint.objects.get_or_create(
                league=league,
                endpoint_type=endpoint_config['endpoint_type'],
                defaults=endpoint_config
            )

            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Endpoint creado: {endpoint.get_endpoint_type_display()}'
                    )
                )
            else:
                if self.verbosity:
                    self.stdout.write(
                        f'Endpoint ya existe: {endpoint.get_endpoint_type_display()}'
                    )

    def scrape_multiple_leagues(self, options):
        """Scraping de múltiples ligas basado en configuración"""
        visibility_type = options['visibility_type']
        
        self.stdout.write(f"Procesando ligas de tipo: {visibility_type}")
        
        # Configuración de ligas históricas conocidas
        historical_leagues = [
            {
                'federation_id': '6754',
                'name': 'ALEVIN MASCULINO 4X4 - Fase Regular',
                'season': '2024-25',
                'category': 'Alevin',
                'visibility_type': 'historical'
                # match_format se auto-detecta como 'alevin_balear'
            },
            {
                'federation_id': '6824',
                'name': 'ALEVIN MASCULINO 4X4 - Fase Final Título',
                'season': '2024-25',
                'category': 'Alevin',
                'visibility_type': 'historical'
                # match_format se auto-detecta como 'alevin_balear'
            },
            {
                'federation_id': '6825',
                'name': 'ALEVIN MASCULINO 4X4 - Circuito Clasificatorio',
                'season': '2024-25',
                'category': 'Alevin',
                'visibility_type': 'historical'
                # match_format se auto-detecta como 'alevin_balear'
            },
            {
                'federation_id': '7898',
                'name': 'ALEVIN MASCULINO 4X4 - Campeonato de Baleares - Grup A',
                'season': '2024-25',
                'category': 'Alevin',
                'visibility_type': 'historical'
                # match_format se auto-detecta como 'alevin_balear'
            },
            {
                'federation_id': '7899',
                'name': 'ALEVIN MASCULINO 4X4 - Campeonato de Baleares - Grup B',
                'season': '2024-25',
                'category': 'Alevin',
                'visibility_type': 'historical'
                # match_format se auto-detecta como 'alevin_balear'
            },
            {
                'federation_id': '7900',
                'name': 'ALEVIN MASCULINO 4X4 - Campeonato de Baleares - Grup C',
                'season': '2024-25',
                'category': 'Alevin',
                'visibility_type': 'historical'
                # match_format se auto-detecta como 'alevin_balear'
            },
            {
                'federation_id': '7905',
                'name': 'ALEVIN MASCULINO 4X4 - Campeonato de Baleares - Grup OR A',
                'season': '2024-25',
                'category': 'Alevin',
                'visibility_type': 'historical'
                # match_format se auto-detecta como 'alevin_balear'
            },
            {
                'federation_id': '7906',
                'name': 'ALEVIN MASCULINO 4X4 - Campeonato de Baleares - Grup OR B',
                'season': '2024-25',
                'category': 'Alevin',
                'visibility_type': 'historical'
                # match_format se auto-detecta como 'alevin_balear'
            },
            {
                'federation_id': '7907',
                'name': 'ALEVIN MASCULINO 4X4 - Campeonato de Baleares - Plata',
                'season': '2024-25',
                'category': 'Alevin',
                'visibility_type': 'historical'
                # match_format se auto-detecta como 'alevin_balear'
            },
            {
                'federation_id': '7920',
                'name': 'ALEVIN MASCULINO 4X4 - Campeonato de Baleares - 5è-6è',
                'season': '2024-25',
                'category': 'Alevin',
                'visibility_type': 'historical'
                # match_format se auto-detecta como 'alevin_balear'
            },
            {
                'federation_id': '7920',
                'name': 'ALEVIN MASCULINO 4X4 - Campeonato de Baleares - FINALS',
                'season': '2024-25',
                'category': 'Alevin',
                'visibility_type': 'historical'
                # match_format se auto-detecta como 'alevin_balear'
            },
            {
                'federation_id': '6738',
                'name': 'INFANTIL MASCULINO - Liga Regular - Cúber',
                'season': '2024-25',
                'category': 'Infantil',
                'visibility_type': 'historical'
            },
            {
                'federation_id': '6739',
                'name': 'INFANTIL MASCULINO - Liga Regular - Gorg Blau',
                'season': '2024-25',
                'category': 'Infantil',
                'visibility_type': 'historical'
            },
            {
                'federation_id': '6819',
                'name': 'INFANTIL MASCULINO - Fase Final título',
                'season': '2024-25',
                'category': 'Infantil',
                'visibility_type': 'historical'
            },
            {
                'federation_id': '7860',
                'name': 'INFANTIL MASCULINO - Fase Final título - FINALS',
                'season': '2024-25',
                'category': 'Infantil',
                'visibility_type': 'historical'
            },
            {
                'federation_id': '6820',
                'name': 'INFANTIL MASCULINO - Circuito Clasificatorio',
                'season': '2024-25',
                'category': 'Infantil',
                'visibility_type': 'historical'
            },
        ]
        
        # Configuración de ligas externas
        external_leagues = [
            {
                'federation_id': '2001',
                'name': 'Liga Catalana Senior',
                'season': '2024-25',
                'category': 'Senior',
                'visibility_type': 'external',
                'is_our_team_related': False
            },
            {
                'federation_id': '2002',
                'name': 'Liga Valenciana Senior',
                'season': '2024-25',
                'category': 'Senior',
                'visibility_type': 'external',
                'is_our_team_related': False
            },
            # Agregar más ligas externas según sea necesario
        ]
        
        leagues_to_process = []
        if visibility_type == 'historical':
            leagues_to_process = historical_leagues
        elif visibility_type == 'external':
            leagues_to_process = external_leagues
        else:
            leagues_to_process = historical_leagues + external_leagues
        
        for league_config in leagues_to_process:
            try:
                self.process_league_config(league_config, options)
            except Exception as e:
                logger.error(f"Error procesando liga {league_config['federation_id']}: {e}")
                self.stdout.write(
                    self.style.ERROR(f"Error procesando liga {league_config['federation_id']}: {e}")
                )

    def process_league_config(self, league_config, options):
        """Procesa una configuración de liga específica"""
        federation_id = league_config['federation_id']
        season = Season.objects.resolve(league_config['season'])
        
        # Obtener categoría
        category = None
        if league_config.get('category'):
            try:
                category = Category.objects.get(name=league_config['category'])
            except Category.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f"Categoría '{league_config['category']}' no encontrada")
                )
        
        # Determinar formato de partido
        match_format = self.get_match_format_for_category(
            league_config.get('category'), 
            league_config.get('match_format', options.get('match_format'))
        )
        
        league_data = {
            'name': league_config['name'],
            'federation_id': federation_id,
            'season': season,
            'visibility_type': league_config['visibility_type'],
            'is_historical': league_config['visibility_type'] == 'historical',
            'is_our_team_related': league_config.get('is_our_team_related', True),
            'category': category,
            'match_format': match_format,
            'base_url': options['base_url']
        }
        
        if self.verbosity:
            self.stdout.write(f"Liga {league_config['name']} - Formato asignado: {match_format}")
        
        if not self.dry_run:
            league, created = League.objects.get_or_create(
                federation_id=federation_id,
                season=season,
                defaults=league_data
            )
            
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"Liga creada: {league.name}")
                )
            else:
                # Actualizar campos existentes
                for key, value in league_data.items():
                    setattr(league, key, value)
                league.save()
                self.stdout.write(
                    self.style.SUCCESS(f"Liga actualizada: {league.name}")
                )
            
            # Configurar endpoints automáticamente
            self.setup_endpoints(league)
            
            # Realizar scraping
            self.perform_scraping(league, options)
        else:
            self.stdout.write(f"[DRY RUN] Se procesaría liga: {league_config['name']}")

    def perform_scraping(self, league, options):
        """Realiza el scraping de datos para una liga"""
        self.stdout.write(f"Iniciando scraping para: {league.name}")
        
        try:
            scraper = FederationScraper(league)
            
            # Scraping completo de todos los endpoints
            if self.verbosity:
                self.stdout.write("Scraping completo de todos los endpoints...")
            
            results = scraper.scrape_all_endpoints()
            
            # Procesar resultados
            total_teams = 0
            total_matches = 0
            total_standings = 0
            
            for endpoint_type, data in results.items():
                if 'error' in data:
                    logger.error(f'{league.name} - {endpoint_type}: {data["error"]}')
                else:
                    teams_count = len(data.get('teams', []))
                    standings_count = len(data.get('standings', []))
                    matches_count = len(data.get('matches', []))
                    
                    total_teams += teams_count
                    total_standings += standings_count
                    total_matches += matches_count
                    
                    if self.verbosity:
                        self.stdout.write(f"  {endpoint_type}: {teams_count} equipos, {matches_count} partidos, {standings_count} clasificaciones")
            
            self.stdout.write(
                self.style.SUCCESS(f"Scraping completado para: {league.name} - "
                                 f"{total_teams} equipos, {total_matches} partidos, {total_standings} clasificaciones")
            )
            
        except Exception as e:
            logger.error(f"Error en scraping de {league.name}: {e}")
            self.stdout.write(
                self.style.ERROR(f"Error en scraping de {league.name}: {e}")
            )

    def log_summary(self, leagues_processed, leagues_created, leagues_updated):
        """Muestra un resumen de la operación"""
        self.stdout.write("\n" + "="*50)
        self.stdout.write("RESUMEN DEL SCRAPING")
        self.stdout.write("="*50)
        self.stdout.write(f"Ligas procesadas: {leagues_processed}")
        self.stdout.write(f"Ligas creadas: {leagues_created}")
        self.stdout.write(f"Ligas actualizadas: {leagues_updated}")
        self.stdout.write("="*50)
