import requests
import time
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Any
from django.utils import timezone
from django.db import transaction
from unidecode import unidecode
from .models import League, Team, Match, Standing, ScrapingEndpoint

logger = logging.getLogger(__name__)


class ScrapingError(Exception):
    """Exception específica para errores de scraping"""
    pass


class BaseParser:
    """Clase base para todos los parsers"""
    
    def __init__(self, league: League):
        self.league = league
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
    
    def fetch_content(self, url: str) -> str:
        """Obtiene el contenido de una URL con manejo de errores"""
        try:
            logger.info(f"Fetching content from: {url}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logger.error(f"Error fetching {url}: {e}")
            raise ScrapingError(f"Failed to fetch {url}: {e}")
    
    def parse_content(self, content: str) -> Dict[str, Any]:
        """Método abstracto que debe implementar cada parser específico"""
        raise NotImplementedError("Subclasses must implement parse_content")
    
    def rate_limit(self, delay: float = 1.0):
        """Aplicar rate limiting entre requests"""
        time.sleep(delay)


class StandingsParser(BaseParser):
    """Parser para tablas de clasificación"""
    
    def parse_content(self, content: str) -> Dict[str, Any]:
        """Parsea una tabla HTML de clasificación"""
        soup = BeautifulSoup(content, 'html.parser')
        
        # Buscar la tabla de clasificación
        table = soup.find('table', class_='clasificacion')
        if not table:
            logger.warning("No se encontró tabla de clasificación")
            return {'teams': [], 'standings': []}
        
        teams = []
        standings = []
        
        rows = table.find_all('tr')[1:]  # Saltar header
        
        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 10:
                continue
                
            try:
                # Extraer datos básicos
                position = int(cells[0].get_text(strip=True).replace('.', ''))
                team_name = cells[1].get_text(strip=True)
                
                # Extraer estadísticas (adaptando a la estructura real)
                played = int(cells[2].get_text(strip=True) or 0)
                won = int(cells[3].get_text(strip=True) or 0)
                drawn = int(cells[4].get_text(strip=True) or 0)  # NP (null points?)
                lost = int(cells[5].get_text(strip=True) or 0)
                sets_for = int(cells[6].get_text(strip=True) or 0)
                sets_against = int(cells[7].get_text(strip=True) or 0)
                points_for = int(cells[8].get_text(strip=True) or 0)
                points_against = int(cells[9].get_text(strip=True) or 0)
                total_points = int(cells[10].get_text(strip=True) or 0)
                
                # Columnas adicionales si existen
                wins_3_0 = int(cells[11].get_text(strip=True) or 0) if len(cells) > 11 else 0
                wins_3_1 = int(cells[12].get_text(strip=True) or 0) if len(cells) > 12 else 0
                losses_2_3 = int(cells[13].get_text(strip=True) or 0) if len(cells) > 13 else 0
                losses_0_3 = int(cells[14].get_text(strip=True) or 0) if len(cells) > 14 else 0
                
                teams.append({
                    'name': team_name,
                    'federation_id': f"{self.league.federation_id}_{team_name.replace(' ', '_').lower()}"
                })
                
                standings.append({
                    'team_name': team_name,
                    'position': position,
                    'played': played,
                    'won': won,
                    'lost': lost,
                    'sets_for': sets_for,
                    'sets_against': sets_against,
                    'points_for': points_for,
                    'points_against': points_against,
                    'total_points': total_points,
                    'wins_3_0': wins_3_0,
                    'wins_3_1': wins_3_1,
                    'losses_2_3': losses_2_3,
                    'losses_0_3': losses_0_3,
                })
                
            except (ValueError, IndexError) as e:
                logger.warning(f"Error parsing row: {e}")
                continue
        
        return {'teams': teams, 'standings': standings}


class MatchesParser(BaseParser):
    """Parser para resultados y calendarios de partidos"""
    
    def parse_content(self, content: str) -> Dict[str, Any]:
        """Parsea la estructura de partidos HTML"""
        soup = BeautifulSoup(content, 'html.parser')
        
        matches = []
        current_round = 1
        
        # Buscar jornadas
        for round_header in soup.find_all('h3'):
            round_text = round_header.get_text(strip=True)
            if 'JORNADA' in round_text.upper():
                try:
                    current_round = int(round_text.split()[-1])
                except (ValueError, IndexError):
                    current_round += 1
        
        # Buscar todos los partidos
        match_divs = soup.find_all('div', class_='info_partido')
        
        for match_div in match_divs:
            try:
                match_data = self._parse_single_match(match_div, current_round)
                if match_data:
                    matches.append(match_data)
            except Exception as e:
                logger.warning(f"Error parsing match: {e}")
                continue
        
        return {'matches': matches}
    
    def _parse_single_match(self, match_div, round_number: int) -> Optional[Dict[str, Any]]:
        """Parsea un div individual de partido"""
        
        # Extraer fecha y hora
        top_div = match_div.find('div', class_='top')
        if not top_div:
            return None
            
        date_text = top_div.find('span', class_='fecha')
        venue_span = top_div.find('span', class_='pabellon')
        city_span = top_div.find('span', class_='municipio')
        
        if not date_text:
            return None
            
        # Parsear fecha
        try:
            date_str = date_text.get_text(strip=True)
            # Formato esperado: "18/10/2025 - 09:30" o "18/10/2025"
            if ' - ' in date_str:
                date_part, time_part = date_str.split(' - ')
                match_datetime = datetime.strptime(f"{date_part} {time_part}", "%d/%m/%Y %H:%M")
            else:
                match_datetime = datetime.strptime(date_str, "%d/%m/%Y")
            
            match_datetime = timezone.make_aware(match_datetime)
            
        except ValueError as e:
            logger.warning(f"Error parsing date {date_str}: {e}")
            return None
        
        # Extraer equipos
        datos_partido = match_div.find('div', class_='datos_partido')
        if not datos_partido:
            return None
            
        team_spans = datos_partido.find_all('span', class_='nombreEquipo')
        if len(team_spans) < 2:
            return None
            
        home_team = team_spans[0].get_text(strip=True)
        away_team = team_spans[1].get_text(strip=True)
        
        # Extraer resultado si existe
        score_spans = datos_partido.find_all('span', class_='marcador')
        home_score = None
        away_score = None
        
        if score_spans and score_spans[0].get_text(strip=True):
            score_text = score_spans[0].get_text(strip=True)
            if ' - ' in score_text:
                try:
                    home_score, away_score = map(int, score_text.split(' - '))
                except ValueError:
                    pass
        
        # Determinar estado
        estado_div = match_div.find('div', class_='estado_partido')
        status = 'scheduled'
        if estado_div:
            if 'finalizado' in estado_div.get('id', '').lower():
                status = 'finished' if home_score is not None else 'scheduled'
        
        return {
            'home_team': home_team,
            'away_team': away_team,
            'match_date': match_datetime,
            'venue': venue_span.get_text(strip=True) if venue_span else '',
            'city': city_span.get_text(strip=True) if city_span else '',
            'round_number': round_number,
            'home_score': home_score,
            'away_score': away_score,
            'status': status,
            'federation_id': f"{self.league.federation_id}_{home_team}_{away_team}_{match_datetime.strftime('%Y%m%d')}"
        }


class FederationScraper:
    """Clase principal para manejar el scraping de la federación"""
    
    def __init__(self, league: League):
        self.league = league
        self.parsers = {
            'table_standings': StandingsParser(league),
            'match_results': MatchesParser(league),
            'match_calendar': MatchesParser(league),
        }
    
    def scrape_endpoint(self, endpoint: ScrapingEndpoint, **kwargs) -> Dict[str, Any]:
        """Ejecuta scraping de un endpoint específico"""
        
        if not endpoint.is_active:
            logger.info(f"Endpoint {endpoint} is inactive, skipping")
            return {}
        
        parser = self.parsers.get(endpoint.parser_type)
        if not parser:
            raise ScrapingError(f"No parser found for type: {endpoint.parser_type}")
        
        url = endpoint.get_full_url(**kwargs)
        content = parser.fetch_content(url)
        
        # Rate limiting
        parser.rate_limit()
        
        return parser.parse_content(content)
    
    @transaction.atomic
    def update_teams(self, teams_data: List[Dict[str, Any]]) -> Dict[str, Team]:
        """Actualiza o crea equipos en la base de datos"""
        team_objects = {}
        
        for team_data in teams_data:
            team, created = Team.objects.get_or_create(
                federation_id=team_data['federation_id'],
                defaults={'name': team_data['name']}
            )
            if not created and team.name != team_data['name']:
                team.name = team_data['name']
                team.save()
            
            # Agregar tanto el nombre original como normalizado para buscar
            team_objects[team_data['name']] = team
            team_objects[self._normalize_team_name(team_data['name'])] = team
            
            if created:
                logger.info(f"Created new team: {team.name}")
        
        return team_objects
    
    def _normalize_team_name(self, name: str) -> str:
        """Normaliza nombres de equipos para comparación"""
        # Remover acentos y convertir a mayúsculas
        normalized = unidecode(name).upper()
        # Remover espacios extra y caracteres especiales
        normalized = ' '.join(normalized.split())
        return normalized
    
    @transaction.atomic
    def update_standings(self, standings_data: List[Dict[str, Any]], team_objects: Dict[str, Team]):
        """Actualiza clasificaciones en la base de datos"""
        
        # Eliminar clasificaciones existentes para esta liga
        Standing.objects.filter(league=self.league).delete()
        
        for standing_data in standings_data:
            team_name = standing_data.pop('team_name')
            team = team_objects.get(team_name)
            
            if not team:
                logger.warning(f"Team not found: {team_name}")
                continue
            
            Standing.objects.create(
                league=self.league,
                team=team,
                **standing_data
            )
        
        logger.info(f"Updated standings for {len(standings_data)} teams")
    
    @transaction.atomic
    def update_matches(self, matches_data: List[Dict[str, Any]], team_objects: Dict[str, Team]):
        """Actualiza partidos en la base de datos"""
        
        for match_data in matches_data:
            home_team_name = match_data.pop('home_team')
            away_team_name = match_data.pop('away_team')
            
            # Buscar equipos tanto por nombre original como normalizado
            home_team = (team_objects.get(home_team_name) or 
                        team_objects.get(self._normalize_team_name(home_team_name)))
            away_team = (team_objects.get(away_team_name) or 
                        team_objects.get(self._normalize_team_name(away_team_name)))
            
            if not home_team or not away_team:
                logger.warning(f"Teams not found: {home_team_name} vs {away_team_name}")
                # Intentar buscar por similitud en la base de datos
                if not home_team:
                    home_team = self._find_similar_team(home_team_name)
                if not away_team:
                    away_team = self._find_similar_team(away_team_name)
                    
                if not home_team or not away_team:
                    logger.error(f"Could not match teams: {home_team_name} vs {away_team_name}")
                    continue
            
            match, created = Match.objects.update_or_create(
                federation_id=match_data.get('federation_id'),
                defaults={
                    'league': self.league,
                    'home_team': home_team,
                    'away_team': away_team,
                    **match_data
                }
            )
            
            if created:
                logger.info(f"Created new match: {match}")
            else:
                logger.info(f"Updated match: {match}")
    
    def _find_similar_team(self, team_name: str) -> Optional[Team]:
        """Busca equipos similares en la base de datos"""
        normalized_name = self._normalize_team_name(team_name)
        
        # Buscar por contenido parcial
        similar_teams = Team.objects.filter(name__icontains=team_name[:10])
        if similar_teams.exists():
            return similar_teams.first()
        
        # Buscar por nombres normalizados
        for team in Team.objects.all():
            if self._normalize_team_name(team.name) == normalized_name:
                return team
        
        return None
    
    def scrape_all_endpoints(self, **kwargs) -> Dict[str, Any]:
        """Ejecuta scraping de todos los endpoints activos de la liga"""
        results = {}
        all_teams = {}
        
        for endpoint in self.league.endpoints.filter(is_active=True):
            try:
                logger.info(f"Scraping endpoint: {endpoint}")
                data = self.scrape_endpoint(endpoint, **kwargs)
                results[endpoint.endpoint_type] = data
                
                # Actualizar equipos si los hay
                if 'teams' in data:
                    new_teams = self.update_teams(data['teams'])
                    all_teams.update(new_teams)
                
                # Actualizar clasificaciones
                if 'standings' in data and all_teams:
                    self.update_standings(data['standings'], all_teams)
                
                # Actualizar partidos
                if 'matches' in data and all_teams:
                    self.update_matches(data['matches'], all_teams)
                    
            except Exception as e:
                logger.error(f"Error scraping endpoint {endpoint}: {e}")
                results[endpoint.endpoint_type] = {'error': str(e)}
        
        return results