from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from videosvoley.core.models import Season
from videosvoley.videos.models import League, Category, ScrapingEndpoint
from videosvoley.videos.scraping import FederationScraper
import logging
import requests
from bs4 import BeautifulSoup
import time

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Scraping masivo de ligas externas desde endpoints de federación'

    def add_arguments(self, parser):
        parser.add_argument(
            '--federation-base-url',
            type=str,
            default='https://www.voleibolib.net',
            help='URL base de la federación'
        )
        parser.add_argument(
            '--season',
            type=str,
            help='Temporada específica (ej: 2024-25). Si no se especifica, usa la actual'
        )
        parser.add_argument(
            '--category',
            type=str,
            help='Categoría específica (ej: Senior, Juvenil)'
        )
        parser.add_argument(
            '--competition-type',
            type=str,
            choices=['regular', 'playoff', 'cup'],
            default='regular',
            help='Tipo de competición'
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
            default=3.0,
            help='Delay entre requests (segundos)'
        )
        parser.add_argument(
            '--max-leagues',
            type=int,
            default=50,
            help='Máximo número de ligas a procesar'
        )

    def handle(self, *args, **options):
        self.verbosity = options['verbose']
        self.dry_run = options['dry_run']
        self.delay = options['delay']
        self.max_leagues = options['max_leagues']
        
        if self.verbosity:
            logger.setLevel(logging.INFO)
        
        try:
            self.scrape_external_leagues(options)
                
        except Exception as e:
            logger.error(f"Error durante el scraping masivo: {e}")
            raise CommandError(f"Error durante el scraping masivo: {e}")

    def scrape_external_leagues(self, options):
        """Scraping masivo de ligas externas"""
        federation_url = options['federation_base_url']
        season = options['season'] or self.get_current_season()
        category = options['category']
        competition_type = options['competition_type']
        
        self.stdout.write(f"Iniciando scraping masivo de ligas externas")
        self.stdout.write(f"Federación: {federation_url}")
        self.stdout.write(f"Temporada: {season}")
        self.stdout.write(f"Categoría: {category or 'Todas'}")
        self.stdout.write(f"Tipo: {competition_type}")
        
        # Descubrir ligas disponibles
        leagues_discovered = self.discover_leagues(federation_url, season, category, competition_type)
        
        if not leagues_discovered:
            self.stdout.write(self.style.WARNING("No se encontraron ligas para procesar"))
            return
        
        self.stdout.write(f"Ligas descubiertas: {len(leagues_discovered)}")
        
        # Procesar ligas
        leagues_processed = 0
        leagues_created = 0
        leagues_updated = 0
        
        for league_info in leagues_discovered[:self.max_leagues]:
            try:
                result = self.process_external_league(league_info, options)
                leagues_processed += 1
                
                if result['created']:
                    leagues_created += 1
                else:
                    leagues_updated += 1
                    
                if self.verbosity:
                    self.stdout.write(f"Procesada: {league_info['name']}")
                    
            except Exception as e:
                logger.error(f"Error procesando liga {league_info.get('name', 'Unknown')}: {e}")
                self.stdout.write(
                    self.style.ERROR(f"Error procesando liga: {e}")
                )
            
            # Rate limiting
            time.sleep(self.delay)
        
        self.log_summary(leagues_processed, leagues_created, leagues_updated)

    def discover_leagues(self, federation_url, season, category, competition_type):
        """Descubre ligas disponibles en la federación"""
        leagues = []
        
        try:
            # Patrones comunes de URLs de ligas
            league_patterns = [
                f"{federation_url}/ligas",
                f"{federation_url}/competiciones",
                f"{federation_url}/temporada-{season}",
                f"{federation_url}/categorias",
            ]
            
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            })
            
            for pattern_url in league_patterns:
                try:
                    if self.verbosity:
                        self.stdout.write(f"Explorando: {pattern_url}")
                    
                    response = session.get(pattern_url, timeout=30)
                    response.raise_for_status()
                    
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Buscar enlaces que parezcan ligas
                    league_links = self.extract_league_links(soup, federation_url, season, category)
                    leagues.extend(league_links)
                    
                    time.sleep(self.delay)
                    
                except requests.RequestException as e:
                    if self.verbosity:
                        self.stdout.write(f"Error accediendo a {pattern_url}: {e}")
                    continue
            
            # Eliminar duplicados
            unique_leagues = []
            seen_ids = set()
            
            for league in leagues:
                league_id = league.get('federation_id')
                if league_id and league_id not in seen_ids:
                    seen_ids.add(league_id)
                    unique_leagues.append(league)
            
            return unique_leagues
            
        except Exception as e:
            logger.error(f"Error descubriendo ligas: {e}")
            return []

    def extract_league_links(self, soup, base_url, season, category):
        """Extrae información de ligas de una página HTML"""
        leagues = []
        
        # Buscar enlaces que contengan patrones de ligas
        links = soup.find_all('a', href=True)
        
        for link in links:
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            # Patrones que indican que es una liga
            league_patterns = [
                'liga', 'competicion', 'categoria', 'division',
                'grupo', 'temporada', 'season'
            ]
            
            if any(pattern in href.lower() or pattern in text.lower() for pattern in league_patterns):
                # Extraer ID de federación del href
                federation_id = self.extract_federation_id(href)
                
                if federation_id:
                    league_info = {
                        'federation_id': federation_id,
                        'name': text or f"Liga {federation_id}",
                        'season': season,
                        'competition_type': 'regular',
                        'base_url': base_url,
                        'source_url': href if href.startswith('http') else f"{base_url}{href}"
                    }
                    
                    # Filtrar por categoría si se especifica
                    if not category or category.lower() in text.lower():
                        leagues.append(league_info)
        
        return leagues

    def extract_federation_id(self, url):
        """Extrae el ID de federación de una URL"""
        import re
        
        # Patrones comunes para IDs de federación
        patterns = [
            r'liga[_-]?(\d+)',
            r'competicion[_-]?(\d+)',
            r'categoria[_-]?(\d+)',
            r'division[_-]?(\d+)',
            r'grupo[_-]?(\d+)',
            r'id[=_](\d+)',
            r'(\d{4,})',  # IDs de 4+ dígitos
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None

    def process_external_league(self, league_info, options):
        """Procesa una liga externa específica"""
        federation_id = league_info['federation_id']
        season = Season.objects.resolve(league_info['season'])
        
        league_data = {
            'name': league_info['name'],
            'federation_id': federation_id,
            'season': season,
            'competition_type': league_info.get('competition_type', 'regular'),
            'visibility_type': 'external',
            'is_historical': False,
            'is_our_team_related': False,
            'base_url': league_info['base_url']
        }
        
        # Obtener categoría si se especifica
        if options['category']:
            try:
                category = Category.objects.get(name=options['category'])
                league_data['category'] = category
            except Category.DoesNotExist:
                if self.verbosity:
                    self.stdout.write(
                        self.style.WARNING(f"Categoría '{options['category']}' no encontrada")
                    )
        
        if not self.dry_run:
            league, created = League.objects.get_or_create(
                federation_id=federation_id,
                defaults=league_data
            )
            
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"Liga externa creada: {league.name}")
                )
            else:
                # Actualizar campos existentes
                for key, value in league_data.items():
                    setattr(league, key, value)
                league.save()
                self.stdout.write(
                    self.style.SUCCESS(f"Liga externa actualizada: {league.name}")
                )
            
            # Realizar scraping básico
            self.perform_basic_scraping(league, options)
            
            return {'created': created, 'league': league}
        else:
            self.stdout.write(f"[DRY RUN] Se procesaría liga externa: {league_info['name']}")
            return {'created': False, 'league': None}

    def perform_basic_scraping(self, league, options):
        """Realiza scraping básico de datos para una liga externa"""
        try:
            scraper = FederationScraper(league)
            
            # Scraping completo de todos los endpoints
            if self.verbosity:
                self.stdout.write(f"Scraping básico para: {league.name}")
            
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
                self.stdout.write(f"Scraping básico completado para: {league.name} - "
                                f"{total_teams} equipos, {total_matches} partidos, {total_standings} clasificaciones")
            
        except Exception as e:
            logger.error(f"Error en scraping básico de {league.name}: {e}")
            if self.verbosity:
                self.stdout.write(
                    self.style.WARNING(f"Error en scraping básico de {league.name}: {e}")
                )

    def get_current_season(self):
        """Obtiene la temporada actual (la activa si está definida)."""
        current = Season.objects.current()
        if current:
            return current.name
        return Season.objects.for_date(timezone.now()).name

    def log_summary(self, leagues_processed, leagues_created, leagues_updated):
        """Muestra un resumen de la operación"""
        self.stdout.write("\n" + "="*50)
        self.stdout.write("RESUMEN DEL SCRAPING MASIVO")
        self.stdout.write("="*50)
        self.stdout.write(f"Ligas procesadas: {leagues_processed}")
        self.stdout.write(f"Ligas creadas: {leagues_created}")
        self.stdout.write(f"Ligas actualizadas: {leagues_updated}")
        self.stdout.write("="*50)
