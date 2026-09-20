from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from videosvoley.videos.models import League, Team, Category
from videosvoley.videos.scraping import FederationScraper
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Extrae solo los equipos de una liga específica y los guarda con la categoría indicada'

    def add_arguments(self, parser):
        parser.add_argument(
            '--league-id',
            type=str,
            required=True,
            help='ID de la federación de la liga de donde extraer equipos'
        )
        parser.add_argument(
            '--category',
            type=str,
            required=True,
            help='Nombre de la categoría a asignar a los equipos (ej: "Senior", "Juvenil")'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Mostrar información detallada'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simular la operación sin guardar en la base de datos'
        )

    def handle(self, *args, **options):
        league_id = options['league_id']
        category_name = options['category']
        verbose = options['verbose']
        dry_run = options['dry_run']

        if verbose:
            logging.basicConfig(level=logging.INFO)

        # Buscar o crear la categoría
        try:
            category = Category.objects.get(name=category_name)
            if verbose:
                self.stdout.write(f'Usando categoría existente: {category.name}')
        except Category.DoesNotExist:
            if dry_run:
                self.stdout.write(
                    self.style.WARNING(f'[DRY RUN] Se crearía la categoría: {category_name}')
                )
                category = None
            else:
                category = Category.objects.create(
                    name=category_name,
                    description=f'Categoría creada automáticamente durante scraping de equipos',
                    is_active=True
                )
                self.stdout.write(
                    self.style.SUCCESS(f'Categoría creada: {category.name}')
                )

        # Verificar si ya existe una liga con ese federation_id
        existing_league = League.objects.filter(federation_id=league_id).first()
        
        if existing_league:
            if verbose:
                self.stdout.write(f'Liga encontrada: {existing_league.name}')
            # Verificar si la categoría ya está asignada a la liga
            existing_categories = existing_league.categories.all()
            if existing_categories and category not in existing_categories:
                existing_cat_names = ', '.join([c.name for c in existing_categories])
                self.stdout.write(
                    self.style.WARNING(
                        f'ADVERTENCIA: La liga existente tiene categorías "{existing_cat_names}" '
                        f'pero se especificó "{category_name}". Se usará la especificada.'
                    )
                )
        else:
            if verbose:
                self.stdout.write(f'No se encontró liga con ID {league_id}. Se usará solo para scraping.')

        # Para equipos de ligas no registradas, necesitamos hacer scraping directo
        # sin usar la infraestructura de ScrapingEndpoint
        
        self.stdout.write(f'Iniciando scraping de equipos de liga: {league_id}')
        if dry_run:
            self.stdout.write(self.style.WARNING('[MODO DRY RUN - No se guardarán cambios]'))

        # Hacer scraping directo usando requests
        import requests
        from bs4 import BeautifulSoup
        from videosvoley.videos.scraping import StandingsParser
        
        # URL correcta para clasificación (JSON endpoint)
        base_url = "https://www.voleibolib.net"
        standings_url = f"{base_url}/JSON/get_clasificacion.asp?id={league_id}"
        
        try:
            # Crear un parser temporal
            temp_league = League(
                name=f"Temp League for scraping {league_id}",
                federation_id=league_id,
                category=category
            )
            parser = StandingsParser(temp_league)
            
            # Obtener contenido directamente
            self.stdout.write(f'Obteniendo equipos desde: {standings_url}')
            content = parser.fetch_content(standings_url)
            
            # Parsear contenido
            parsed_data = parser.parse_content(content)
            
            # Simular resultados como si viniesen del scraper
            results = {
                'standings': parsed_data
            }
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error obteniendo datos de la liga: {e}')
            )
            results = {
                'standings': {'error': str(e)}
            }
        
        try:
            teams_processed = 0
            teams_created = 0
            teams_updated = 0
            
            # Procesar todos los endpoints que contengan equipos
            for endpoint_type, data in results.items():
                if 'error' in data:
                    self.stdout.write(
                        self.style.ERROR(f'{endpoint_type}: Error - {data["error"]}')
                    )
                    continue
                
                teams_data = data.get('teams', [])
                if not teams_data:
                    continue
                
                self.stdout.write(f'\n=== Procesando equipos de {endpoint_type} ===')
                
                for team_data in teams_data:
                    teams_processed += 1
                    team_name = team_data.get('name', '').strip()
                    team_federation_id = team_data.get('federation_id', '')
                    
                    if not team_name:
                        continue
                    
                    if verbose:
                        self.stdout.write(f'Procesando: {team_name}')
                    
                    if dry_run:
                        # En modo dry run, solo mostrar lo que se haría
                        existing = Team.objects.filter(federation_id=team_federation_id).first() if team_federation_id else None
                        if existing:
                            self.stdout.write(f'  [DRY RUN] Se actualizaría: {existing.name} -> categoría {category_name}')
                        else:
                            self.stdout.write(f'  [DRY RUN] Se crearía: {team_name} con categoría {category_name}')
                        continue
                    
                    # Buscar equipo existente por federation_id
                    existing_team = None
                    if team_federation_id:
                        existing_team = Team.objects.filter(federation_id=team_federation_id).first()
                    
                    if existing_team:
                        # Actualizar equipo existente
                        updated = False
                        if existing_team.category != category:
                            existing_team.category = category
                            updated = True
                        if existing_team.name != team_name:
                            # Solo actualizar el nombre si no es un duplicado por nombre normalizado
                            from videosvoley.videos.utils import normalize_team_name
                            if normalize_team_name(existing_team.name) != normalize_team_name(team_name):
                                existing_team.name = team_name
                                updated = True
                            else:
                                if verbose:
                                    self.stdout.write(f'  - Variación de nombre detectada: "{existing_team.name}" vs "{team_name}"')
                        
                        if updated:
                            existing_team.save()
                            teams_updated += 1
                            if verbose:
                                self.stdout.write(f'  ✓ Actualizado: {existing_team.name}')
                        else:
                            if verbose:
                                self.stdout.write(f'  - Sin cambios: {existing_team.name}')
                    else:
                        # Buscar duplicado por nombre normalizado antes de crear
                        from videosvoley.videos.utils import find_duplicate_team_by_name
                        duplicate_team = find_duplicate_team_by_name(team_name, category=category)
                        
                        if duplicate_team:
                            # Actualizar el equipo duplicado con el nuevo federation_id
                            duplicate_team.federation_id = team_federation_id
                            duplicate_team.is_active = True
                            duplicate_team.save()
                            teams_updated += 1
                            if verbose:
                                self.stdout.write(f'  ✓ Duplicado encontrado y actualizado: "{duplicate_team.name}" (federation_id: {team_federation_id})')
                        else:
                            # Crear nuevo equipo
                            new_team = Team.objects.create(
                                name=team_name,
                                federation_id=team_federation_id,
                                category=category,
                                is_active=True
                            )
                            teams_created += 1
                            if verbose:
                                self.stdout.write(f'  ✓ Creado: {new_team.name}')

            # Mostrar resumen
            self.stdout.write(f'\n=== RESUMEN ===')
            self.stdout.write(f'Equipos procesados: {teams_processed}')
            if not dry_run:
                self.stdout.write(
                    self.style.SUCCESS(f'Equipos creados: {teams_created}')
                )
                self.stdout.write(
                    self.style.SUCCESS(f'Equipos actualizados: {teams_updated}')
                )
                self.stdout.write(
                    self.style.SUCCESS(f'Categoría asignada: {category.name}')
                )
            else:
                self.stdout.write(self.style.WARNING('Ejecución en modo DRY RUN - No se guardaron cambios'))

        except Exception as e:
            logger.error(f'Error durante scraping de equipos: {e}')
            raise CommandError(f'Error durante scraping de equipos: {e}')