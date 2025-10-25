from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from videosvoley.videos.models import Club, Team
import requests
import logging
import time
from difflib import SequenceMatcher
import unicodedata

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Scraping de clubes desde voleibolib.net con matching inteligente de equipos'

    def add_arguments(self, parser):
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Mostrar información detallada'
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=1.0,
            help='Delay entre requests en segundos (default: 1.0)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo mostrar qué se haría sin guardar cambios'
        )
        parser.add_argument(
            '--match-teams',
            action='store_true',
            help='Ejecutar matching de equipos existentes con clubes'
        )

    def handle(self, *args, **options):
        self.verbose = options['verbose']
        self.delay = options['delay']
        self.dry_run = options['dry_run']
        self.match_teams = options['match_teams']

        if self.verbose:
            logging.basicConfig(level=logging.INFO)

        self.stdout.write('Iniciando scraping de clubes desde voleibolib.net')

        try:
            # 1. Obtener lista de clubes
            clubs_data = self.fetch_clubs_list()
            self.stdout.write(f'Encontrados {len(clubs_data)} clubes')

            # 2. Procesar cada club
            created_count = 0
            updated_count = 0
            
            for club_basic in clubs_data:
                club_id = club_basic['ID']
                club_name = club_basic['Nombre']
                
                if self.verbose:
                    self.stdout.write(f'Procesando club: {club_name} (ID: {club_id})')
                
                # Obtener detalles del club
                club_details = self.fetch_club_details(club_id)
                
                if club_details and club_details.get('Nombre'):
                    club, created = self.create_or_update_club(club_id, club_details)
                    if created:
                        created_count += 1
                        if self.verbose:
                            self.stdout.write(
                                self.style.SUCCESS(f'✓ Creado: {club.official_name}')
                            )
                    else:
                        updated_count += 1
                        if self.verbose:
                            self.stdout.write(
                                self.style.WARNING(f'↻ Actualizado: {club.official_name}')
                            )
                elif self.verbose:
                    self.stdout.write(f'⚠ Sin datos válidos para club ID {club_id}')
                
                # Delay entre requests
                time.sleep(self.delay)

            # 3. Matching con equipos existentes si se solicita
            matched_count = 0
            if self.match_teams:
                matched_count = self.match_teams_to_clubs()

            # Resumen final
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n=== Resumen ===\n'
                    f'Clubes creados: {created_count}\n'
                    f'Clubes actualizados: {updated_count}\n'
                    f'Equipos asociados: {matched_count}'
                )
            )

        except Exception as e:
            logger.error(f'Error durante scraping: {e}')
            raise CommandError(f'Error durante scraping: {e}')

    def fetch_clubs_list(self):
        """Obtiene la lista de clubes desde la API"""
        url = 'https://www.voleibolib.net/JSON/get_clubes.asp'
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data.get('items', [])
        except Exception as e:
            raise CommandError(f'Error obteniendo lista de clubes: {e}')

    def fetch_club_details(self, club_id):
        """Obtiene los detalles de un club específico"""
        url = f'https://www.voleibolib.net/JSON/get_datos_club.asp?id={club_id}'
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            # Los datos vienen dentro de un array 'items'
            items = data.get('items', [])
            if items:
                return items[0]  # Devolver el primer (y único) elemento
            
            return None
        except Exception as e:
            logger.warning(f'Error obteniendo detalles del club {club_id}: {e}')
            return None

    def create_or_update_club(self, club_id, club_data):
        """Crea o actualiza un club con los datos obtenidos"""
        club_name = self.clean_string(club_data.get('Nombre', ''))
        
        if self.dry_run:
            self.stdout.write(f'[DRY RUN] Crearía/actualizaría club: {club_name or "N/A"}')
            # Crear objeto mock para dry-run
            class MockClub:
                def __init__(self, name):
                    self.official_name = name
            return MockClub(club_name), False

        club, created = Club.objects.update_or_create(
            federation_id=str(club_id),
            defaults={
                'official_name': self.clean_string(club_data.get('Nombre', '')),
                'president': self.clean_string(club_data.get('Presidente', '')),
                'address': self.clean_string(club_data.get('Direccion', '')),
                'phone': self.clean_string(club_data.get('telefono', '')),  # Note: lowercase in JSON
                'email': self.clean_string(club_data.get('mail', '')),      # Note: 'mail' not 'Email'
                'venue_name': self.clean_string(club_data.get('campo', '')), # Note: lowercase
                'venue_address': self.clean_string(club_data.get('direccion_campo', '')), # Note: underscore
                'province': self.clean_string(club_data.get('provincia', '')), # Note: lowercase
                'instagram': self.clean_url(club_data.get('instagram', '')),
                'facebook': self.clean_url(club_data.get('facebook', '')),
                'twitter': self.clean_url(club_data.get('twitter', '')),
                'website': self.clean_url(club_data.get('url', '')),  # Note: 'url' not 'Web'
                'logo_url': f'https://voleibolib.federatio.com/fichas/clubes/{club_id}.jpg'
            }
        )
        return club, created

    def match_teams_to_clubs(self):
        """Ejecuta matching inteligente entre equipos y clubes"""
        self.stdout.write('\nIniciando matching de equipos con clubes...')
        
        teams_without_club = Team.objects.filter(club__isnull=True)
        clubs = Club.objects.all()
        matched_count = 0

        for team in teams_without_club:
            best_match = self.find_best_club_match(team, clubs)
            
            if best_match:
                club, similarity = best_match
                if similarity > 0.55:  # Umbral de confianza
                    if not self.dry_run:
                        team.club = club
                        # Si el equipo no tiene sponsor_name, usar el nombre actual
                        if not team.sponsor_name:
                            team.sponsor_name = team.name
                        team.save()
                    
                    matched_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✓ Matched: {team.name} → {club.official_name} '
                            f'(confianza: {similarity:.2f})'
                        )
                    )
                elif self.verbose:
                    self.stdout.write(
                        self.style.WARNING(
                            f'? Posible match: {team.name} → {club.official_name} '
                            f'(confianza: {similarity:.2f}) - No aplicado automáticamente'
                        )
                    )

        return matched_count

    def find_best_club_match(self, team, clubs):
        """Encuentra la mejor coincidencia entre un equipo y los clubes"""
        team_normalized = self.normalize_name(team.name)
        best_match = None
        best_similarity = 0

        for club in clubs:
            club_normalized = self.normalize_name(club.official_name)
            
            # Comparar nombre completo
            similarity = SequenceMatcher(None, team_normalized, club_normalized).ratio()
            
            # Comparar palabras clave (buscar coincidencias parciales)
            team_words = set(team_normalized.split())
            club_words = set(club_normalized.split())
            
            # Si hay palabras comunes significativas, aumentar similaridad
            common_words = team_words.intersection(club_words)
            if common_words:
                # Filtrar palabras muy comunes que no son distintivas
                stopwords = {'club', 'volei', 'voley', 'voleibol', 'cv', 'esportiu', 'deportivo'}
                meaningful_common = common_words - stopwords
                
                if meaningful_common:
                    word_similarity = len(meaningful_common) / max(len(team_words), len(club_words))
                    similarity = max(similarity, word_similarity)

            if similarity > best_similarity:
                best_similarity = similarity
                best_match = (club, similarity)

        return best_match if best_similarity > 0.3 else None

    def normalize_name(self, name):
        """Normaliza un nombre para comparación"""
        from videosvoley.videos.utils import normalize_team_name
        return normalize_team_name(name)

    def clean_string(self, value):
        """Limpia una cadena de texto"""
        if not value or value == 'null':
            return ''
        return str(value).strip()

    def clean_url(self, value):
        """Limpia y valida una URL"""
        if not value or value == 'null' or not str(value).strip():
            return ''
        
        url = str(value).strip()
        if url and not url.startswith(('http://', 'https://')):
            url = f'https://{url}'
        
        return url