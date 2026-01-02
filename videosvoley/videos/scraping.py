import requests
import time
import logging
import json
from datetime import datetime
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Any
from django.utils import timezone
from django.db import transaction, models
from unidecode import unidecode
from .models import League, Team, Match, Standing, ScrapingEndpoint

logger = logging.getLogger(__name__)


def validate_volleyball_score(home_score: int, away_score: int, league) -> bool:
    """
    Valida si un resultado de voleibol es válido según el formato de la liga.
    
    Args:
        home_score: Puntos del equipo local
        away_score: Puntos del equipo visitante
        league: Objeto League con el formato de partido configurado
    
    Returns:
        bool: True si el resultado es válido, False en caso contrario
    """
    # Resultados imposibles en cualquier formato
    impossible_scores = [(0, 0), (1, 1), (2, 2)]
    if (home_score, away_score) in impossible_scores:
        logger.warning(f"Resultado imposible detectado: {home_score}-{away_score}")
        return False
    
    if league.match_format == 'standard':
        # 5 sets máximo, ganar 3
        return (home_score == 3 and away_score < 3) or (away_score == 3 and home_score < 3)
    
    elif league.match_format == 'alevin_balear':
        # 3 sets, jugar los 3 - resultados posibles: 3-0, 2-1, 1-2, 0-3
        valid_alevin_scores = [
            (3, 0), (2, 1), (1, 2), (0, 3)
        ]
        return (home_score, away_score) in valid_alevin_scores
    
    elif league.match_format == 'tournament_3sets':
        # 3 sets máximo, ganar 2
        return (home_score == 2 and away_score < 2) or (away_score == 2 and home_score < 2)
    
    elif league.match_format == 'custom':
        # Usar valores personalizados
        max_sets = league.custom_max_sets or 5
        sets_to_win = league.custom_sets_to_win or 3
        return (home_score == sets_to_win and away_score < sets_to_win) or \
               (away_score == sets_to_win and home_score < sets_to_win)
    
    # Fallback para ligas sin formato definido (compatibilidad)
    return (home_score == 3 and away_score < 3) or (away_score == 3 and home_score < 3)


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
                # Validar resultado antes de marcar como finalizado
                if home_score is not None and away_score is not None:
                    if validate_volleyball_score(home_score, away_score, self.league):
                        status = 'finished'
                    else:
                        logger.warning(f"Partido marcado como finalizado pero con resultado inválido: {home_score}-{away_score}")
                        # No marcar como finalizado si el resultado es inválido
                        status = 'scheduled'
                        home_score = None
                        away_score = None
                else:
                    status = 'scheduled'
        
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
        }


class CalendarParser(BaseParser):
    """Parser específico para calendarios con estructura de tabla"""
    
    def parse_content(self, content: str) -> Dict[str, Any]:
        """Parsea el HTML del calendario con tablas calendario-completo"""
        soup = BeautifulSoup(content, 'html.parser')
        
        matches = []
        
        # Buscar todas las tablas de calendario
        calendar_tables = soup.find_all('table', class_='calendario-completo')
        
        for table in calendar_tables:
            current_round = 1
            
            # Buscar el header de jornada
            round_header = table.find('tr', class_='jornada')
            if round_header:
                th = round_header.find('th')
                if th:
                    header_text = th.get_text(strip=True)
                    # Extraer número de jornada: "Jornada 1 18/10/2025"
                    try:
                        parts = header_text.split()
                        if len(parts) >= 2 and parts[0].lower() == 'jornada':
                            current_round = int(parts[1])
                    except (ValueError, IndexError):
                        pass
            
            # Procesar todas las filas de partidos (excluyendo header)
            rows = table.find_all('tr')
            for row in rows:
                if 'jornada' in row.get('class', []):
                    continue  # Saltar headers de jornada
                
                try:
                    match_data = self._parse_calendar_row(row, current_round)
                    if match_data:
                        matches.append(match_data)
                except Exception as e:
                    logger.warning(f"Error parsing calendar row: {e}")
                    continue
        
        return {'matches': matches}
    
    def _parse_calendar_row(self, row, round_number: int) -> Optional[Dict[str, Any]]:
        """Parsea una fila individual del calendario"""
        cells = row.find_all('td')
        if len(cells) < 3:
            return None
            
        # Extraer equipos
        home_team = cells[0].get_text(strip=True)
        away_team = cells[1].get_text(strip=True)
        
        # Saltar si algún equipo "Descansa"
        if home_team.lower() == 'descansa' or away_team.lower() == 'descansa':
            return None
            
        # Extraer fecha y hora
        date_cell = cells[2]
        date_html = date_cell.decode_contents() if hasattr(date_cell, 'decode_contents') else str(date_cell)
        
        # El HTML puede contener: <strong>18/10/2025<br>09:30</strong>
        # Extraer fecha y hora
        date_text = date_cell.get_text(strip=True)
        
        try:
            # Limpiar y normalizar el texto de fecha
            date_text = date_text.replace('\n', ' ').strip()
            
            # Detectar si es un resultado de partido (ej: "3 - 2", "0 - 3")
            import re
            score_pattern = r'^(\d+)\s*-\s*(\d+)$'
            score_match = re.match(score_pattern, date_text)
            
            if score_match:
                # Es un resultado, no una fecha
                home_score = int(score_match.group(1))
                away_score = int(score_match.group(2))
                
                # Validar resultado antes de procesarlo
                if not validate_volleyball_score(home_score, away_score, self.league):
                    logger.warning(f"Resultado inválido detectado en calendario: {home_score}-{away_score}")
                    # No procesar resultados inválidos
                    return None
                
                # Para resultados, buscar el partido existente y solo actualizar el resultado
                # No crear un nuevo partido sin fecha
                return {
                    'home_team': home_team,
                    'away_team': away_team,
                    'match_date': None,  # No hay fecha en resultados
                    'venue': '',
                    'city': '',
                    'round_number': round_number,
                    'home_score': home_score,
                    'away_score': away_score,
                    'status': 'finished',
                    'is_result_only': True,  # Marcar que es solo un resultado
                }
            
            # Detectar si la fecha y hora están pegadas (ej: "18/10/202509:30")
            date_pattern = r'(\d{2}/\d{2}/\d{4})(\d{2}:\d{2})?'
            match = re.match(date_pattern, date_text)
            
            if match:
                date_str = match.group(1)
                time_str = match.group(2) if match.group(2) else None
            else:
                # Fallback: intentar parsear por espacios
                parts = date_text.split()
                if len(parts) >= 2:
                    date_str = parts[0]
                    time_str = parts[1] if ':' in parts[1] else None
                else:
                    date_str = date_text
                    time_str = None
            
            # Crear datetime object
            if time_str:
                match_datetime = datetime.strptime(f"{date_str} {time_str}", "%d/%m/%Y %H:%M")
            else:
                # Si no hay hora, usar medianoche para indicar que la hora está pendiente
                match_datetime = datetime.strptime(date_str, "%d/%m/%Y")
                # Mantener hora 00:00 para indicar que está pendiente de confirmar
            
            match_datetime = timezone.make_aware(match_datetime)
            
        except ValueError as e:
            logger.warning(f"Error parsing calendar date '{date_text}': {e}")
            return None
        
        return {
            'home_team': home_team,
            'away_team': away_team,
            'match_date': match_datetime,
            'venue': '',  # No disponible en formato calendario
            'city': '',   # No disponible en formato calendario
            'round_number': round_number,
            'home_score': None,  # No hay resultados en calendario
            'away_score': None,  # No hay resultados en calendario
            'status': 'scheduled',
        }


class JSONMatchesParser(BaseParser):
    """Parser para el endpoint JSON de partidos de la federación"""
    
    def parse_content(self, content: str) -> Dict[str, Any]:
        """Parsea el JSON de partidos de la federación"""
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON: {e}")
            return {'matches': [], 'teams': []}
        
        matches = []
        teams = []
        
        # Navegar por la estructura jerárquica del JSON
        for categoria in data.get('categorias', []):
            categoria_name = categoria.get('nombre', '')
            
            for competicion in categoria.get('competiciones', []):
                competicion_name = competicion.get('nombre', '')
                
                for fase in competicion.get('fases', []):
                    fase_name = fase.get('nombre', '')
                    
                    for grupo in fase.get('grupos', []):
                        grupo_name = grupo.get('nombre', '')
                        grupo_id = grupo.get('id', '')
                        
                        # Procesar partidos del grupo
                        for partido_data in grupo.get('partidos', []):
                            match_data = self._parse_single_json_match(partido_data, grupo_id, categoria_name)
                            if match_data:
                                matches.append(match_data)
                                
                                # Extraer equipos para actualización
                                if match_data.get('home_team'):
                                    teams.append({
                                        'name': match_data['home_team'],
                                        'federation_id': f"{grupo_id}_{match_data['home_team'].replace(' ', '_').lower()}",
                                        'federation_club_id': str(partido_data.get('ID_CLUB_LOCAL', ''))
                                    })
                                if match_data.get('away_team'):
                                    teams.append({
                                        'name': match_data['away_team'],
                                        'federation_id': f"{grupo_id}_{match_data['away_team'].replace(' ', '_').lower()}",
                                        'federation_club_id': str(partido_data.get('ID_CLUB_VISITANTE', ''))
                                    })
        
        return {'matches': matches, 'teams': teams}
    
    def _parse_single_json_match(self, partido_data: Dict, grupo_id: str, categoria_name: str) -> Optional[Dict[str, Any]]:
        """Parsea un partido individual del JSON"""
        
        # Extraer equipos
        home_team = (partido_data.get('ELOCAL') or '').strip()
        away_team = (partido_data.get('EVISITANTE') or '').strip()
        
        if not home_team or not away_team:
            return None
        
        # Parsear fecha y hora
        fecha_str = partido_data.get('FECHA', '')
        hora_str = partido_data.get('HORA', '')
        
        if not fecha_str:
            return None
        
        try:
            # Formato: "24/10/2025" y "18:15"
            if hora_str:
                match_datetime = datetime.strptime(f"{fecha_str} {hora_str}", "%d/%m/%Y %H:%M")
            else:
                match_datetime = datetime.strptime(fecha_str, "%d/%m/%Y")
            
            match_datetime = timezone.make_aware(match_datetime)
            
        except ValueError as e:
            logger.warning(f"Error parsing date {fecha_str} {hora_str}: {e}")
            return None
        
        # Extraer resultados
        home_score = partido_data.get('RESULTADO_LOCAL')
        away_score = partido_data.get('RESULTADO_VISITANTE')
        
        # Determinar estado basado en resultados y acta
        status = 'scheduled'
        if home_score is not None and away_score is not None:
            # Validar resultado antes de marcar como finalizado
            if validate_volleyball_score(home_score, away_score, self.league):
                status = 'finished'
            else:
                logger.warning(f"Resultado inválido en JSON: {home_score}-{away_score}")
                # No marcar como finalizado si el resultado es inválido
                status = 'scheduled'
                home_score = None
                away_score = None
        elif partido_data.get('acta_html'):
            # Si hay acta pero no resultados, podría estar en progreso o finalizado sin score
            status = 'finished'
        
        # Extraer información de árbitros y personal técnico
        referee1 = (partido_data.get('arbitro1') or '').strip()
        referee2 = (partido_data.get('arbitro2') or '').strip()
        scorer = (partido_data.get('anotador') or '').strip()
        timekeeper = (partido_data.get('cronometrador') or '').strip()
        delegate = (partido_data.get('delegado') or '').strip()
        
        # Información del campo
        field_name = (partido_data.get('Campo') or '').strip()
        field_address = (partido_data.get('Direccion_Campo') or '').strip()
        city = (partido_data.get('Municipio') or '').strip()
        
        # IDs de la federación
        federation_club_local_id = str(partido_data.get('ID_CLUB_LOCAL', ''))
        federation_club_away_id = str(partido_data.get('ID_CLUB_VISITANTE', ''))
        
        return {
            'home_team': home_team,
            'away_team': away_team,
            'match_date': match_datetime,
            'venue': field_name,
            'city': city,
            'round_number': 1,  # El JSON no incluye jornada, usar 1 por defecto
            'home_score': home_score if home_score is not None else None,
            'away_score': away_score if away_score is not None else None,
            'status': status,
            'referee1': referee1,
            'referee2': referee2,
            'scorer': scorer,
            'timekeeper': timekeeper,
            'delegate': delegate,
            'field_address': field_address,
            'federation_club_local_id': federation_club_local_id,
            'federation_club_away_id': federation_club_away_id,
            'federation_id': str(partido_data.get('ID', '')),
            'acta_html': (partido_data.get('acta_html') or '').strip(),
            'categoria': categoria_name,
            'grupo_id': grupo_id,
        }


class JSONUnifiedParser(BaseParser):
    """Parser unificado para endpoints JSON de la federación (op=1, op=2, etc.)"""
    
    def __init__(self, league: League, op_type: str = '1'):
        super().__init__(league)
        self.op_type = op_type  # '1' para próximos, '2' para resultados, etc.
    
    def parse_content(self, content: str) -> Dict[str, Any]:
        """Parsea el JSON de partidos de la federación según el tipo de operación"""
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON (op={self.op_type}): {e}")
            return {'matches': [], 'teams': []}
        
        matches = []
        teams = []
        
        # Navegar por la estructura jerárquica del JSON
        for categoria in data.get('categorias', []):
            categoria_name = categoria.get('nombre', '')
            
            for competicion in categoria.get('competiciones', []):
                competicion_name = competicion.get('nombre', '')
                
                for fase in competicion.get('fases', []):
                    fase_name = fase.get('nombre', '')
                    
                    for grupo in fase.get('grupos', []):
                        grupo_name = grupo.get('nombre', '')
                        grupo_id = grupo.get('id', '')
                        
                        # Procesar partidos del grupo
                        for partido_data in grupo.get('partidos', []):
                            match_data = self._parse_single_json_match(partido_data, grupo_id, categoria_name)
                            if match_data:
                                matches.append(match_data)
                                
                                # Extraer equipos para actualización
                                if match_data.get('home_team'):
                                    teams.append({
                                        'name': match_data['home_team'],
                                        'federation_id': f"{grupo_id}_{match_data['home_team'].replace(' ', '_').lower()}",
                                        'federation_club_id': str(partido_data.get('ID_CLUB_LOCAL', ''))
                                    })
                                if match_data.get('away_team'):
                                    teams.append({
                                        'name': match_data['away_team'],
                                        'federation_id': f"{grupo_id}_{match_data['away_team'].replace(' ', '_').lower()}",
                                        'federation_club_id': str(partido_data.get('ID_CLUB_VISITANTE', ''))
                                    })
        
        return {'matches': matches, 'teams': teams}
    
    def _parse_single_json_match(self, partido_data: Dict, grupo_id: str, categoria_name: str) -> Optional[Dict[str, Any]]:
        """Parsea un partido individual del JSON según el tipo de operación"""
        
        # Extraer equipos
        home_team = (partido_data.get('ELOCAL') or '').strip()
        away_team = (partido_data.get('EVISITANTE') or '').strip()
        
        if not home_team or not away_team:
            return None
        
        # Parsear fecha y hora
        fecha_str = partido_data.get('FECHA', '')
        hora_str = partido_data.get('HORA', '')
        
        if not fecha_str:
            return None
        
        try:
            # Formato: "24/10/2025" y "18:15"
            if hora_str:
                match_datetime = datetime.strptime(f"{fecha_str} {hora_str}", "%d/%m/%Y %H:%M")
            else:
                match_datetime = datetime.strptime(fecha_str, "%d/%m/%Y")
            
            match_datetime = timezone.make_aware(match_datetime)
            
        except ValueError as e:
            logger.warning(f"Error parsing date {fecha_str} {hora_str}: {e}")
            return None
        
        # Extraer resultados según el tipo de operación
        home_score = partido_data.get('RESULTADO_LOCAL')
        away_score = partido_data.get('RESULTADO_VISITANTE')
        
        # Determinar estado y validaciones según op_type
        if self.op_type == '2':  # Resultados
            # Verificar que el partido tenga resultados válidos
            if home_score is None or away_score is None:
                logger.debug(f"Partido sin resultados completos: {home_team} vs {away_team}")
                return None
            
            # Validar resultado antes de marcar como finalizado
            if validate_volleyball_score(home_score, away_score, self.league):
                status = 'finished'
            else:
                logger.warning(f"Resultado inválido en JSON unificado: {home_score}-{away_score}")
                # No procesar resultados inválidos
                return None
        else:  # Próximos (op=1) u otros
            # Los partidos próximos pueden no tener resultados
            status = 'scheduled'
            if home_score is not None and away_score is not None:
                # Validar resultado antes de marcar como finalizado
                if validate_volleyball_score(home_score, away_score, self.league):
                    status = 'finished'
                else:
                    logger.warning(f"Resultado inválido en JSON unificado (próximos): {home_score}-{away_score}")
                    # No marcar como finalizado si el resultado es inválido
                    status = 'scheduled'
                    home_score = None
                    away_score = None
            elif partido_data.get('acta_html'):
                status = 'finished'
        
        # Extraer información de árbitros y personal técnico
        referee1 = (partido_data.get('arbitro1') or '').strip()
        referee2 = (partido_data.get('arbitro2') or '').strip()
        scorer = (partido_data.get('anotador') or '').strip()
        timekeeper = (partido_data.get('cronometrador') or '').strip()
        delegate = (partido_data.get('delegado') or '').strip()
        
        # Información del campo
        field_name = (partido_data.get('Campo') or '').strip()
        field_address = (partido_data.get('Direccion_Campo') or '').strip()
        city = (partido_data.get('Municipio') or '').strip()
        
        # IDs de la federación
        federation_club_local_id = str(partido_data.get('ID_CLUB_LOCAL', ''))
        federation_club_away_id = str(partido_data.get('ID_CLUB_VISITANTE', ''))
        
        # Información adicional
        acta_html = (partido_data.get('acta_html') or '').strip()
        comentario = (partido_data.get('COMENTARIO') or '').strip()
        resultado_web = partido_data.get('RESULTADO_WEB', False)
        
        return {
            'home_team': home_team,
            'away_team': away_team,
            'match_date': match_datetime,
            'venue': field_name,
            'city': city,
            'round_number': 1,  # El JSON no incluye jornada, usar 1 por defecto
            'home_score': home_score if home_score is not None else None,
            'away_score': away_score if away_score is not None else None,
            'status': status,
            'referee1': referee1,
            'referee2': referee2,
            'scorer': scorer,
            'timekeeper': timekeeper,
            'delegate': delegate,
            'field_address': field_address,
            'federation_club_local_id': federation_club_local_id,
            'federation_club_away_id': federation_club_away_id,
            'federation_id': str(partido_data.get('ID', '')),
            'acta_html': acta_html,
            'comentario': comentario,
            'resultado_web': resultado_web,
            'categoria': categoria_name,
            'grupo_id': grupo_id,
            'op_type': self.op_type,  # Para identificar el tipo de datos
        }


class FederationScraper:
    """Clase principal para manejar el scraping de la federación"""
    
    def __init__(self, league: League):
        self.league = league
        self.parsers = {
            'table_standings': StandingsParser(league),
            'match_results': MatchesParser(league),
            'match_calendar': CalendarParser(league),
            'json_matches': JSONUnifiedParser(league, op_type='1'),  # Próximos
            'json_results': JSONUnifiedParser(league, op_type='2'),  # Resultados
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
    
    def process_json_unified(self, json_url: str, op_type: str = '1', filter_by_db_leagues: bool = True) -> Dict[str, Any]:
        """
        Procesa datos JSON de forma unificada y eficiente.
        
        Args:
            json_url: URL del endpoint JSON
            op_type: Tipo de operación ('1' para próximos, '2' para resultados, etc.)
            filter_by_db_leagues: Si True, solo procesa grupos que tenemos en la BD
        
        Returns:
            dict: Resultados del procesamiento
        """
        try:
            logger.info(f"Procesando JSON unificado (op={op_type}) desde: {json_url}")
            
            # Obtener datos del JSON
            response = requests.get(json_url, timeout=30)
            response.raise_for_status()
            json_data = json.loads(response.text)
            
            # Obtener IDs de ligas que tenemos en la base de datos (si se requiere filtrado)
            db_league_ids = set()
            if filter_by_db_leagues:
                db_league_ids = set(League.objects.filter(federation_id__isnull=False).values_list('federation_id', flat=True))
                logger.info(f"Filtrando por {len(db_league_ids)} ligas en BD: {sorted(db_league_ids)}")
            
            # Crear mapeo de grupo_id a league para procesamiento eficiente
            group_league_map = {}
            if filter_by_db_leagues:
                for grupo_id in db_league_ids:
                    league = League.objects.filter(federation_id=grupo_id, is_active=True).first()
                    if league:
                        group_league_map[grupo_id] = league
                        logger.debug(f"Mapped group {grupo_id} to league: {league.name}")
            
            total_results = {
                'leagues_processed': 0,
                'leagues_errors': 0,
                'matches_created': 0,
                'matches_updated': 0,
                'teams_created': 0,
                'errors': []
            }
            
            # Procesar cada categoría del JSON
            for categoria in json_data.get('categorias', []):
                categoria_name = categoria.get('nombre', '')
                
                for competicion in categoria.get('competiciones', []):
                    competicion_name = competicion.get('nombre', '')
                    
                    for fase in competicion.get('fases', []):
                        fase_name = fase.get('nombre', '')
                        
                        for grupo in fase.get('grupos', []):
                            grupo_id = grupo.get('id', '')
                            
                            # Filtrar por grupos de la BD si se requiere
                            if filter_by_db_leagues and str(grupo_id) not in db_league_ids:
                                logger.debug(f"Skipping group {grupo_id} - not in database")
                                continue
                            
                            # Obtener liga correspondiente
                            league = None
                            if filter_by_db_leagues:
                                league = group_league_map.get(str(grupo_id))
                                if not league:
                                    logger.warning(f"League not found for group {grupo_id}")
                                    continue
                            else:
                                # Si no filtramos, usar la liga del scraper
                                league = self.league
                            
                            logger.info(f'Procesando grupo {grupo_id} -> {league.name}')
                            
                            try:
                                # Procesar partidos del grupo
                                partidos = grupo.get('partidos', [])
                                if partidos:
                                    logger.info(f'Encontrados {len(partidos)} partidos en {league.name}')
                                    
                                    # Procesar partidos usando el parser unificado
                                    matches_created, matches_updated = self._process_json_matches_unified(
                                        league, partidos, categoria_name, grupo_id, op_type
                                    )
                                    
                                    total_results['matches_created'] += matches_created
                                    total_results['matches_updated'] += matches_updated
                                    
                                    logger.info(f'Procesados en {league.name}: Creados: {matches_created}, Actualizados: {matches_updated}')
                                else:
                                    logger.info(f'No se encontraron partidos en {league.name}')
                                
                                total_results['leagues_processed'] += 1
                                
                            except Exception as e:
                                error_msg = f'Error procesando {league.name}: {str(e)}'
                                logger.error(error_msg, exc_info=True)
                                
                                total_results['leagues_errors'] += 1
                                total_results['errors'].append({
                                    'league': league.name,
                                    'error': str(e)
                                })
            
            logger.info(f'Procesamiento JSON unificado completado: {total_results["leagues_processed"]} ligas procesadas, {total_results["matches_created"]} partidos creados, {total_results["matches_updated"]} partidos actualizados')
            
            return {
                'status': 'success',
                'leagues_processed': total_results['leagues_processed'],
                'leagues_errors': total_results['leagues_errors'],
                'matches_created': total_results['matches_created'],
                'matches_updated': total_results['matches_updated'],
                'teams_created': total_results['teams_created'],
                'errors': total_results['errors']
            }
            
        except Exception as e:
            error_msg = f'Error general en procesamiento JSON unificado: {str(e)}'
            logger.error(error_msg, exc_info=True)
            return {'status': 'error', 'message': error_msg}
    
    def _process_json_matches_unified(self, league, partidos_data, categoria_name, grupo_id, op_type):
        """Procesa los partidos encontrados en un grupo específico del JSON usando el parser unificado"""
        from unidecode import unidecode
        from datetime import datetime
        from django.utils import timezone
        
        matches_created = 0
        matches_updated = 0
        
        for partido_data in partidos_data:
            try:
                # Usar el parser unificado para procesar el partido
                parser = JSONUnifiedParser(league, op_type=op_type)
                match_data = parser._parse_single_json_match(partido_data, grupo_id, categoria_name)
                
                if not match_data:
                    continue
                
                # Buscar equipos
                home_team = self._find_team_by_name(match_data['home_team'], league)
                away_team = self._find_team_by_name(match_data['away_team'], league)
                
                if not home_team or not away_team:
                    logger.debug(f'Saltando partido: {match_data["home_team"]} vs {match_data["away_team"]} (equipos no encontrados)')
                    continue
                
                # Buscar partido existente
                match = Match.objects.filter(
                    home_team=home_team,
                    away_team=away_team,
                    match_date=match_data['match_date']
                ).first()
                
                if match:
                    # Actualizar partido existente
                    match.home_score = match_data['home_score']
                    match.away_score = match_data['away_score']
                    match.status = match_data['status']
                    match.venue = match_data.get('venue', '')
                    match.city = match_data.get('city', '')
                    match.referee1 = match_data.get('referee1', '')
                    match.referee2 = match_data.get('referee2', '')
                    match.scorer = match_data.get('scorer', '')
                    match.timekeeper = match_data.get('timekeeper', '')
                    match.delegate = match_data.get('delegate', '')
                    match.field_address = match_data.get('field_address', '')
                    match.federation_id = match_data.get('federation_id', '')
                    match.acta_html = match_data.get('acta_html', '')
                    match.save()
                    matches_updated += 1
                    
                    logger.debug(f'Actualizado: {home_team.name} {match.home_score}-{match.away_score} {away_team.name}')
                else:
                    # Validar resultado antes de crear nuevo partido
                    home_score = match_data['home_score']
                    away_score = match_data['away_score']
                    status = match_data['status']
                    
                    if home_score is not None and away_score is not None:
                        if not validate_volleyball_score(home_score, away_score, league):
                            logger.warning(f"Resultado inválido para nuevo partido: {home_team.name} vs {away_team.name} - {home_score}-{away_score}")
                            # No crear partido con resultado inválido
                            continue
                    
                    # Crear nuevo partido
                    match = Match.objects.create(
                        league=league,
                        home_team=home_team,
                        away_team=away_team,
                        match_date=match_data['match_date'],
                        home_score=home_score,
                        away_score=away_score,
                        status=status,
                        venue=match_data.get('venue', ''),
                        city=match_data.get('city', ''),
                        referee1=match_data.get('referee1', ''),
                        referee2=match_data.get('referee2', ''),
                        scorer=match_data.get('scorer', ''),
                        timekeeper=match_data.get('timekeeper', ''),
                        delegate=match_data.get('delegate', ''),
                        field_address=match_data.get('field_address', ''),
                        federation_id=match_data.get('federation_id', ''),
                        acta_html=match_data.get('acta_html', ''),
                        round_number=match_data.get('round_number', 1)
                    )
                    matches_created += 1
                    
                    logger.debug(f'Creado: {home_team.name} {match.home_score}-{match.away_score} {away_team.name}')
                    
            except Exception as e:
                logger.error(f'Error procesando partido {partido_data.get("ELOCAL", "Unknown")} vs {partido_data.get("EVISITANTE", "Unknown")}: {str(e)}')
                continue
        
        return matches_created, matches_updated
    
    @transaction.atomic
    def update_teams(self, teams_data: List[Dict[str, Any]]) -> Dict[str, Team]:
        """Actualiza o crea equipos en la base de datos, detectando equipos retirados"""
        team_objects = {}
        current_federation_ids = set()
        
        # Procesar equipos encontrados en el scraping
        for team_data in teams_data:
            current_federation_ids.add(team_data['federation_id'])
            
            # Buscar equipo existente por federation_id primero
            team = Team.objects.filter(federation_id=team_data['federation_id']).first()
            
            if not team:
                # Si no existe por federation_id, buscar por nombre normalizado para evitar duplicados
                from videosvoley.videos.utils import find_duplicate_team_by_name
                # Usar la primera categoría de la liga (para compatibilidad con ligas multi-categoría)
                league_category = self.league.categories.first()
                duplicate_team = find_duplicate_team_by_name(
                    team_data['name'],
                    category=league_category
                )
                
                if duplicate_team:
                    # Si encontramos un duplicado, actualizar su federation_id y usar ese equipo
                    logger.info(f"Found duplicate team by name: '{team_data['name']}' -> '{duplicate_team.name}' (ID: {duplicate_team.id})")
                    duplicate_team.federation_id = team_data['federation_id']
                    duplicate_team.is_active = True
                    duplicate_team.save()
                    team = duplicate_team
                    created = False
                else:
                    # Crear nuevo equipo
                    # Usar la primera categoría de la liga (para compatibilidad con ligas multi-categoría)
                    league_category = self.league.categories.first()
                    team = Team.objects.create(
                        name=team_data['name'],
                        federation_id=team_data['federation_id'],
                        category=league_category,
                        is_active=True
                    )
                    created = True
            else:
                created = False
            
            # Actualizar nombre, categoría y estado si el equipo ya existía
            updated = False
            if not created and team.name != team_data['name']:
                # Solo actualizar el nombre si no es un duplicado por nombre normalizado
                from videosvoley.videos.utils import normalize_team_name
                if normalize_team_name(team.name) != normalize_team_name(team_data['name']):
                    team.name = team_data['name']
                    updated = True
                else:
                    logger.info(f"Team name variation detected but keeping original: '{team.name}' vs '{team_data['name']}'")
            
            # Asignar/actualizar categoría si la liga tiene categorías y el equipo no la tiene o es diferente
            league_category = self.league.categories.first()
            if league_category and team.category != league_category:
                team.category = league_category
                updated = True
                logger.info(f"Assigned category '{league_category}' to team: {team.name}")
            
            # Reactivar equipo si había sido marcado como inactivo y ahora aparece de nuevo
            if not team.is_active:
                team.is_active = True
                updated = True
                logger.info(f"Reactivated team: {team.name} - now appears in federation data again")
            
            if updated:
                team.save()
            
            # Agregar tanto el nombre original como normalizado para buscar
            team_objects[team_data['name']] = team
            team_objects[self._normalize_team_name(team_data['name'])] = team
            
            if created:
                league_category = self.league.categories.first()
                logger.info(f"Created new team: {team.name} with category: {league_category}")
        
        # DETECTAR EQUIPOS RETIRADOS: buscar equipos que participaban en esta liga pero ya no aparecen
        if current_federation_ids:  # Solo si hay datos para comparar
            # Obtener equipos que tenían partidos en esta liga pero ya no aparecen en el scraping
            existing_teams_in_league = Team.objects.filter(
                models.Q(home_matches__league=self.league) | models.Q(away_matches__league=self.league)
            ).filter(is_active=True).distinct()
            
            withdrawn_teams = []
            for team in existing_teams_in_league:
                if team.federation_id not in current_federation_ids:
                    team.is_active = False
                    team.save()
                    withdrawn_teams.append(team)
                    logger.warning(
                        f"Team marked as inactive (withdrawn): {team.name} "
                        f"(federation_id: {team.federation_id}) - no longer appears in {self.league.name}"
                    )
            
            if withdrawn_teams:
                logger.info(f"Detected {len(withdrawn_teams)} withdrawn teams in {self.league.name}")
                # Los partidos de estos equipos se marcarán como 'withdrawn' en update_matches()
        
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
        """Actualiza partidos en la base de datos evitando duplicados"""
        from datetime import timedelta
        
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
            
            match_date = match_data.get('match_date')
            round_number = match_data.get('round_number')
            is_result_only = match_data.get('is_result_only', False)
            
            # Si es solo un resultado (sin fecha), buscar partido existente para actualizar
            if is_result_only:
                existing_match = Match.objects.filter(
                    league=self.league,
                    home_team=home_team,
                    away_team=away_team,
                    round_number=round_number,
                    is_friendly=False
                ).first()
                
                if existing_match:
                    # Validar resultado antes de actualizar
                    home_score = match_data.get('home_score')
                    away_score = match_data.get('away_score')
                    
                    if home_score is not None and away_score is not None:
                        if validate_volleyball_score(home_score, away_score, self.league):
                            # Solo actualizar resultado y estado
                            existing_match.home_score = home_score
                            existing_match.away_score = away_score
                            existing_match.status = match_data.get('status', 'finished')
                            existing_match.save()
                            logger.info(f"Updated result for existing match: {home_team.name} vs {away_team.name} - {home_score}-{away_score}")
                        else:
                            logger.warning(f"Resultado inválido para partido existente: {home_team.name} vs {away_team.name} - {home_score}-{away_score}")
                    else:
                        logger.warning(f"Partido existente sin resultados válidos: {home_team.name} vs {away_team.name}")
                else:
                    logger.warning(f"Could not find existing match to update result: {home_team.name} vs {away_team.name}")
                continue
            
            # ESTRATEGIA MEJORADA DE BÚSQUEDA PARA EVITAR DUPLICADOS:
            # 1. Buscar por liga + equipos + jornada (criterio principal)
            # 2. Si no existe, buscar por liga + equipos + fecha (mismo día) como fallback
            # 3. Si existe, hacer merge inteligente de datos
            # 4. Si no existe, crear nuevo partido
            
            existing_match = None
            
            # PRIORIDAD 1: Buscar por jornada (más preciso para detectar cambios de fecha)
            if round_number:
                existing_match = Match.objects.filter(
                    league=self.league,
                    home_team=home_team,
                    away_team=away_team,
                    round_number=round_number,
                    is_friendly=False  # Solo actualizar partidos oficiales, no amistosos
                ).first()
                
                if existing_match:
                    logger.info(f"Found existing match by round: {home_team.name} vs {away_team.name} in round {round_number}")
            
            # PRIORIDAD 2: Si no se encontró por jornada, buscar por fecha (fallback)
            if not existing_match and match_date:
                date_start = match_date.replace(hour=0, minute=0, second=0, microsecond=0)
                date_end = date_start + timedelta(days=1)
                
                existing_match = Match.objects.filter(
                    league=self.league,
                    home_team=home_team,
                    away_team=away_team,
                    match_date__gte=date_start,
                    match_date__lt=date_end,
                    is_friendly=False  # Solo actualizar partidos oficiales, no amistosos
                ).first()
                
                if existing_match:
                    logger.info(f"Found existing match by date: {home_team.name} vs {away_team.name} on {match_date.date()}")
            
            # Crear o actualizar el partido con merge inteligente
            if existing_match:
                # MERGE INTELIGENTE: Actualizar solo campos que:
                # 1. Tienen valor en los nuevos datos (no None y no vacío)
                # 2. O están vacíos/None en el partido existente
                # 3. O representan información más específica (ej: hora específica vs 00:00)
                updated_fields = []
                
                for key, new_value in match_data.items():
                    # Saltar campos que no existen en el modelo
                    if not hasattr(existing_match, key):
                        continue
                        
                    current_value = getattr(existing_match, key, None)
                    
                    # Determinar si debemos actualizar el campo
                    should_update = False
                    
                    # Si el valor actual está vacío y el nuevo tiene contenido
                    if self._is_empty_value(current_value) and not self._is_empty_value(new_value):
                        should_update = True
                    # Si el nuevo valor tiene más información (ej: hora específica vs 00:00)
                    elif key == 'match_date' and new_value and current_value:
                        # Actualizar si la nueva fecha tiene hora específica y la actual no
                        if new_value.hour != 0 and current_value.hour == 0:
                            should_update = True
                        # O si la fecha es completamente diferente (cambio de día)
                        elif new_value.date() != current_value.date():
                            should_update = True
                    # Si tenemos nuevos resultados y el partido estaba sin resultados
                    elif key in ['home_score', 'away_score', 'status'] and new_value is not None:
                        if key == 'status' and new_value == 'finished' and current_value != 'finished':
                            should_update = True
                        elif key in ['home_score', 'away_score'] and current_value is None:
                            should_update = True
                    # Para campos de árbitros y personal técnico, actualizar si hay nueva información
                    elif key in ['referee1', 'referee2', 'scorer', 'timekeeper', 'delegate', 'field_address']:
                        if not self._is_empty_value(new_value) and new_value != current_value:
                            should_update = True
                    # Para otros campos, actualizar si el nuevo valor no está vacío y es diferente
                    elif not self._is_empty_value(new_value) and new_value != current_value:
                        should_update = True
                    
                    if should_update:
                        setattr(existing_match, key, new_value)
                        updated_fields.append(key)
                
                if updated_fields:
                    existing_match.save()
                    logger.info(f"Updated match fields: {', '.join(updated_fields)} for {existing_match}")
                    # Log específico para cambios de fecha
                    if 'match_date' in updated_fields:
                        logger.info(f"Match date updated from {current_value} to {new_value} for {existing_match}")
                else:
                    logger.debug(f"No updates needed for match: {existing_match}")
                    
            else:
                # Crear nuevo partido - filtrar campos que no existen en el modelo
                # Validar resultado antes de crear nuevo partido
                home_score = match_data.get('home_score')
                away_score = match_data.get('away_score')
                
                if home_score is not None and away_score is not None:
                    if not validate_volleyball_score(home_score, away_score, self.league):
                        logger.warning(f"Resultado inválido para nuevo partido: {home_team.name} vs {away_team.name} - {home_score}-{away_score}")
                        # No crear partido con resultado inválido
                        continue
                
                valid_match_data = {}
                for key, value in match_data.items():
                    if hasattr(Match, key):
                        valid_match_data[key] = value
                
                match = Match.objects.create(
                    league=self.league,
                    home_team=home_team,
                    away_team=away_team,
                    **valid_match_data
                )
                logger.info(f"Created new match: {match}")
        
        # MARCAR PARTIDOS COMO WITHDRAWN: partidos que involucran equipos inactivos
        self._mark_withdrawn_matches()
    
    def _mark_withdrawn_matches(self):
        """Marca como 'withdrawn' los partidos que involucran equipos inactivos"""
        # Encontrar partidos en esta liga que involucran equipos inactivos
        withdrawn_matches = Match.objects.filter(
            league=self.league,
            status__in=['scheduled', 'postponed'],  # Solo marcar partidos que aún no han comenzado
            is_friendly=False  # No marcar amistosos como retirados
        ).filter(
            models.Q(home_team__is_active=False) | models.Q(away_team__is_active=False)
        )
        
        count = 0
        for match in withdrawn_matches:
            # Verificar que realmente hay un equipo inactivo involucrado
            if not match.home_team.is_active or not match.away_team.is_active:
                inactive_teams = []
                if not match.home_team.is_active:
                    inactive_teams.append(match.home_team.name)
                if not match.away_team.is_active:
                    inactive_teams.append(match.away_team.name)
                
                match.status = 'withdrawn'
                match.save()
                count += 1
                
                logger.warning(
                    f"Match marked as withdrawn: {match.home_team.name} vs {match.away_team.name} "
                    f"on {match.match_date.strftime('%d/%m/%Y')} - inactive teams: {', '.join(inactive_teams)}"
                )
        
        if count > 0:
            logger.info(f"Marked {count} matches as withdrawn in {self.league.name}")
    
    def _is_empty_value(self, value) -> bool:
        """Determina si un valor está vacío o es None"""
        if value is None:
            return True
        if isinstance(value, str) and value.strip() == '':
            return True
        return False
    
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
    
    def get_max_rounds(self) -> int:
        """
        Determina el número máximo de jornadas para la liga.
        Usa la jornada más alta de la BD con un margen de seguridad.
        """
        # Intentar obtener de la base de datos
        from django.db.models import Max
        max_round = Match.objects.filter(league=self.league).aggregate(Max('round_number'))['round_number__max']
        
        if max_round and max_round > 0:
            # Agregar un margen de seguridad pequeño (puede haber más jornadas)
            result = max_round + 3
            logger.debug(f"Max rounds from DB: {max_round}, using {result} with safety margin")
            return result
        
        # Si no hay datos en BD, usar un valor por defecto razonable
        # Las ligas típicas tienen entre 18-30 jornadas
        logger.debug(f"No matches in DB, using default max rounds: 26")
        return 26  # Valor por defecto más conservador
    
    def scrape_all_results_rounds(self, delay: float = 1.0) -> Dict[str, Any]:
        """
        Scrapea todas las jornadas de resultados disponibles.
        Itera desde la jornada 1 hasta que no encuentre más datos.
        
        Args:
            delay: Tiempo de espera entre jornadas en segundos
            
        Returns:
            Dict con estadísticas del scraping
        """
        results_endpoint = self.league.endpoints.filter(
            endpoint_type='results',
            is_active=True
        ).first()
        
        if not results_endpoint:
            logger.warning(f"No results endpoint found for {self.league.name}")
            return {'error': 'No results endpoint configured'}
        
        max_rounds = self.get_max_rounds()
        total_matches = 0
        rounds_processed = 0
        rounds_with_data = 0
        all_teams = {}
        
        logger.info(f"Starting results scraping for {self.league.name}, checking up to {max_rounds} rounds")
        
        for round_num in range(1, max_rounds + 1):
            try:
                logger.info(f"Scraping round {round_num}/{max_rounds} for {self.league.name}")
                
                # Scrapear esta jornada específica
                data = self.scrape_endpoint(results_endpoint, round=round_num)
                
                if 'error' in data:
                    logger.warning(f"Error in round {round_num}: {data['error']}")
                    continue
                
                # Si no hay partidos, podría ser que esta jornada no existe aún
                if not data.get('matches'):
                    logger.debug(f"No matches found in round {round_num}")
                    # Si llevamos 3 jornadas consecutivas sin datos, probablemente terminamos
                    if rounds_processed - rounds_with_data >= 3:
                        logger.info(f"No data in 3 consecutive rounds, stopping at round {round_num}")
                        break
                    rounds_processed += 1
                    continue
                
                rounds_with_data += 1
                rounds_processed += 1
                
                # Actualizar equipos si los hay
                if 'teams' in data:
                    new_teams = self.update_teams(data['teams'])
                    all_teams.update(new_teams)
                
                # Actualizar partidos
                if 'matches' in data:
                    matches_count = len(data['matches'])
                    self.update_matches(data['matches'], all_teams)
                    total_matches += matches_count
                    logger.info(f"Round {round_num}: {matches_count} matches processed")
                
                # Rate limiting entre jornadas
                if round_num < max_rounds:
                    time.sleep(delay)
                    
            except Exception as e:
                logger.error(f"Error scraping round {round_num}: {e}", exc_info=True)
                rounds_processed += 1
                continue
        
        result_summary = {
            'status': 'success',
            'rounds_processed': rounds_processed,
            'rounds_with_data': rounds_with_data,
            'total_matches': total_matches,
        }
        
        logger.info(
            f"Completed results scraping for {self.league.name}: "
            f"{rounds_with_data} rounds with data, {total_matches} total matches"
        )
        
        return result_summary
    
    def enrich_matches_with_json(self, json_url: str = "https://www.voleibolib.net/JSON/get_partidos_desglose_competiciones.asp") -> Dict[str, Any]:
        """
        Enriquece partidos existentes con información del endpoint JSON de la federación.
        Este endpoint proporciona información adicional como árbitros, personal técnico, etc.
        OPTIMIZADO: Solo procesa grupos/ligas que tenemos en la base de datos.
        """
        try:
            logger.info(f"Enriching matches with JSON data from: {json_url}")
            
            # Obtener IDs de ligas que tenemos en la base de datos
            db_league_ids = set(League.objects.filter(federation_id__isnull=False).values_list('federation_id', flat=True))
            logger.info(f"Found {len(db_league_ids)} leagues in database: {sorted(db_league_ids)}")
            
            # Obtener datos del JSON
            response = requests.get(json_url, timeout=30)
            response.raise_for_status()
            
            # Parsear JSON
            json_data = json.loads(response.text)
            
            enriched_count = 0
            new_matches_count = 0
            processed_groups = 0
            skipped_groups = 0
            
            # Recopilar todos los partidos de grupos que tenemos en la BD
            all_matches = []
            group_league_map = {}  # Mapeo grupo_id -> league
            
            # Primero, crear mapeo de grupo_id a league para evitar búsquedas repetidas
            for grupo_id in db_league_ids:
                league = League.objects.filter(federation_id=grupo_id, is_active=True).first()
                if league:
                    group_league_map[grupo_id] = league
                    logger.debug(f"Mapped group {grupo_id} to league: {league.name}")
            
            # Procesar cada categoría del JSON
            for categoria in json_data.get('categorias', []):
                categoria_name = categoria.get('nombre', '')
                logger.debug(f"Processing category: {categoria_name}")
                
                # Procesar partidos de esta categoría
                for competicion in categoria.get('competiciones', []):
                    for fase in competicion.get('fases', []):
                        for grupo in fase.get('grupos', []):
                            grupo_id = str(grupo.get('id', ''))
                            grupo_nombre = grupo.get('nombre', '')
                            
                            # Solo procesar si tenemos esta liga en la BD
                            if grupo_id in db_league_ids:
                                league = group_league_map.get(grupo_id)
                                if league:
                                    logger.info(f"Processing group: {grupo_nombre} (ID: {grupo_id}) -> League: {league.name}")
                                    processed_groups += 1
                                    
                                    # Recopilar partidos de este grupo
                                    for partido_data in grupo.get('partidos', []):
                                        # Añadir información de la liga al partido para facilitar el procesamiento
                                        partido_data['_league'] = league
                                        partido_data['_grupo_id'] = grupo_id
                                        all_matches.append(partido_data)
                                else:
                                    logger.warning(f"League not found for group {grupo_nombre} (ID: {grupo_id})")
                            else:
                                logger.debug(f"Skipping group {grupo_nombre} (ID: {grupo_id}) - not in database")
                                skipped_groups += 1
            
            logger.info(f"Collected {len(all_matches)} matches from {processed_groups} groups (skipped {skipped_groups} groups)")
            
            # Procesar todos los partidos recopilados
            for partido_data in all_matches:
                league = partido_data.pop('_league')
                grupo_id = partido_data.pop('_grupo_id')
                
                # Verificar si el partido ya existe
                json_match_id = str(partido_data.get('ID', ''))
                match_exists = Match.objects.filter(federation_id=json_match_id).exists() if json_match_id else False
                
                enriched = self._enrich_single_match(partido_data, league)
                if enriched:
                    if match_exists:
                        enriched_count += 1
                    else:
                        new_matches_count += 1
            
            result = {
                'status': 'success',
                'enriched_matches': enriched_count,
                'new_matches': new_matches_count,
                'processed_groups': processed_groups,
                'skipped_groups': skipped_groups,
                'total_matches_processed': len(all_matches)
            }
            
            logger.info(f"JSON enrichment completed: {enriched_count} matches enriched, {new_matches_count} new matches created from {processed_groups} groups")
            return result
            
        except Exception as e:
            logger.error(f"Error enriching matches with JSON: {e}")
            return {'error': str(e)}
    
    def _enrich_single_match(self, partido_data: Dict, league: League) -> bool:
        """Enriquece un partido existente con datos del JSON"""
        
        # Buscar partido existente por federation_id del JSON
        json_match_id = str(partido_data.get('ID', ''))
        if not json_match_id:
            return False
        
        logger.debug(f"Intentando enriquecer partido JSON ID={json_match_id} para liga {league.name}")
        
        match = None
        
        # Primero intentar buscar por federation_id del JSON
        try:
            match = Match.objects.get(federation_id=json_match_id)
        except Match.DoesNotExist:
            # Si no existe, buscar por otros criterios
            # Extraer datos del partido del JSON
            fecha_str = partido_data.get('FECHA', '')
            hora_str = partido_data.get('HORA', '')
            equipo_local = (partido_data.get('ELOCAL') or '').strip()
            equipo_visitante = (partido_data.get('EVISITANTE') or '').strip()
            club_local_id = str(partido_data.get('ID_CLUB_LOCAL', ''))
            club_visitante_id = str(partido_data.get('ID_CLUB_VISITANTE', ''))
            
            if fecha_str and (equipo_local and equipo_visitante or (club_local_id and club_visitante_id)):
                try:
                    # Convertir fecha del formato DD/MM/YYYY a datetime
                    from datetime import datetime
                    fecha_obj = datetime.strptime(fecha_str, '%d/%m/%Y').date()
                    
                    # ESTRATEGIA 1: Buscar por IDs de clubes (más preciso)
                    if club_local_id and club_visitante_id:
                        from videosvoley.videos.models import Club
                        
                        # Buscar clubes por federation_id
                        club_local = Club.objects.filter(federation_id=club_local_id).first()
                        club_visitante = Club.objects.filter(federation_id=club_visitante_id).first()
                        
                        if club_local and club_visitante:
                            # Buscar partido por fecha y clubes
                            matches_fecha = Match.objects.filter(
                                league=league,
                                match_date__date=fecha_obj
                            )
                            
                            for match_candidate in matches_fecha:
                                # Verificar si los equipos pertenecen a los clubes correctos
                                local_team = match_candidate.home_team
                                visitante_team = match_candidate.away_team
                                
                                if (local_team and local_team.club == club_local and 
                                    visitante_team and visitante_team.club == club_visitante):
                                    match = match_candidate
                                    logger.info(f"Partido encontrado por IDs de clubes: {match}")
                                    break
                                elif (local_team and local_team.club == club_visitante and 
                                      visitante_team and visitante_team.club == club_local):
                                    match = match_candidate
                                    logger.info(f"Partido encontrado por IDs de clubes (orden invertido): {match}")
                                    break
                    
                    # ESTRATEGIA 2: Si no se encontró por clubes, buscar por nombres (fallback)
                    if not match and equipo_local and equipo_visitante:
                        # Normalizar nombres para búsqueda más flexible
                        def normalize_team_name(name):
                            """Normaliza nombres de equipos para búsqueda flexible"""
                            from videosvoley.videos.utils import normalize_team_name as normalize_team_name_util
                            return normalize_team_name_util(name)
                        
                        equipo_local_norm = normalize_team_name(equipo_local)
                        equipo_visitante_norm = normalize_team_name(equipo_visitante)
                        logger.info(f"Nombres normalizados - JSON: local='{equipo_local_norm}', visitante='{equipo_visitante_norm}'")
                        
                        # Buscar partido por fecha, equipos y liga con búsqueda flexible
                        matches_fecha = Match.objects.filter(
                            league=league,
                            match_date__date=fecha_obj
                        )
                        
                        for match_candidate in matches_fecha:
                            # Normalizar nombres de la BD
                            local_bd = normalize_team_name(match_candidate.home_team_text or (match_candidate.home_team.name if match_candidate.home_team else ""))
                            visitante_bd = normalize_team_name(match_candidate.away_team_text or (match_candidate.away_team.name if match_candidate.away_team else ""))
                            logger.info(f"Nombres normalizados - BD: local='{local_bd}', visitante='{visitante_bd}'")
                            
                            # Verificar si coinciden (considerando que pueden estar en orden diferente)
                            # Usar búsqueda de subcadenas más flexible
                            def teams_match(team1_json, team2_json, team1_bd, team2_bd):
                                """Verifica si dos equipos coinciden considerando subcadenas"""
                                # Buscar coincidencias parciales
                                match1 = (team1_json in team1_bd or team1_bd in team1_json) and \
                                        (team2_json in team2_bd or team2_bd in team2_json)
                                match2 = (team1_json in team2_bd or team2_bd in team1_json) and \
                                        (team2_json in team1_bd or team1_bd in team2_json)
                                return match1 or match2
                            
                            if teams_match(equipo_local_norm, equipo_visitante_norm, local_bd, visitante_bd):
                                match = match_candidate
                                logger.info(f"Partido encontrado por búsqueda flexible: {match}")
                                break
                        
                except ValueError:
                    # Error en formato de fecha
                    pass
        
        if not match:
            logger.info(f"No se encontró partido para enriquecer: ID={json_match_id}, fecha={fecha_str}, local={equipo_local}, visitante={equipo_visitante}")
            
            # Intentar crear un partido nuevo si no existe
            try:
                created = self._create_match_from_json(partido_data, league)
                if created:
                    logger.info(f"Created new match from JSON: ID={json_match_id}")
                    return True
            except Exception as e:
                logger.error(f"Error creating new match from JSON: {e}")
            
            # Buscar partidos similares para debug
            if fecha_str and equipo_local and equipo_visitante:
                try:
                    from datetime import datetime
                    fecha_obj = datetime.strptime(fecha_str, '%d/%m/%Y').date()
                    matches_similares = Match.objects.filter(
                        league=league,
                        match_date__date=fecha_obj
                    )
                    logger.info(f"Partidos encontrados en la misma fecha: {matches_similares.count()}")
                    for m in matches_similares[:3]:
                        logger.info(f"  - {m}: local='{m.home_team_text or (m.home_team.name if m.home_team else 'N/A')}', visitante='{m.away_team_text or (m.away_team.name if m.away_team else 'N/A')}'")
                except Exception as e:
                    logger.info(f"Error buscando partidos similares: {e}")
            return False
        
        # Extraer datos de enriquecimiento
        referee1 = (partido_data.get('arbitro1') or '').strip()
        referee2 = (partido_data.get('arbitro2') or '').strip()
        scorer = (partido_data.get('anotador') or '').strip()
        timekeeper = (partido_data.get('cronometrador') or '').strip()
        delegate = (partido_data.get('delegado') or '').strip()
        field_address = (partido_data.get('Direccion_Campo') or '').strip()
        
        # Actualizar campos si están vacíos o si hay nueva información
        updated = False
        
        if referee1 and not match.referee1:
            match.referee1 = referee1
            updated = True
        
        if referee2 and not match.referee2:
            match.referee2 = referee2
            updated = True
        
        if scorer and not match.scorer:
            match.scorer = scorer
            updated = True
        
        if timekeeper and not match.timekeeper:
            match.timekeeper = timekeeper
            updated = True
        
        if delegate and not match.delegate:
            match.delegate = delegate
            updated = True
        
        if field_address and not match.field_address:
            match.field_address = field_address
            updated = True
        
        # Actualizar IDs de clubes de la federación
        federation_club_local_id = str(partido_data.get('ID_CLUB_LOCAL', ''))
        federation_club_away_id = str(partido_data.get('ID_CLUB_VISITANTE', ''))
        
        if federation_club_local_id and not match.federation_club_local_id:
            match.federation_club_local_id = federation_club_local_id
            updated = True
        
        if federation_club_away_id and not match.federation_club_away_id:
            match.federation_club_away_id = federation_club_away_id
            updated = True
        
        # Actualizar acta si está disponible
        acta_html = (partido_data.get('acta_html') or '').strip()
        if acta_html and not match.acta_html:
            # Construir URL completa del acta
            partido_id = partido_data.get('ID')
            if partido_id:
                acta_url = f"https://voleibolib.federatio.com/actas/{partido_id}/{acta_html}"
                match.acta_html = acta_url
                updated = True
                logger.debug(f"URL del acta construida: {acta_url}")
            else:
                logger.warning(f"No se pudo construir URL del acta: falta ID del partido")
        
        if updated:
            match.save()
            logger.debug(f"Enriched match: {match}")
        
        return updated
    
    def _build_acta_url(self, partido_data: Dict) -> str:
        """Construye la URL completa del acta usando el ID del partido"""
        acta_html = (partido_data.get('acta_html') or '').strip()
        if acta_html and partido_data.get('ID'):
            return f"https://voleibolib.federatio.com/actas/{partido_data.get('ID')}/{acta_html}"
        return ''
    
    def _create_match_from_json(self, partido_data: Dict, league: League) -> bool:
        """Crea un partido nuevo desde datos JSON si no existe"""
        
        # Solo crear si no existe ya
        json_match_id = str(partido_data.get('ID', ''))
        if not json_match_id:
            return False
            
        # Verificar si ya existe un partido con este federation_id
        if Match.objects.filter(federation_id=json_match_id).exists():
            logger.debug(f"Match with federation_id {json_match_id} already exists, skipping creation")
            return False
        
        # Extraer equipos
        home_team_name = (partido_data.get('ELOCAL') or '').strip()
        away_team_name = (partido_data.get('EVISITANTE') or '').strip()
        
        if not home_team_name or not away_team_name:
            return False
        
        # Buscar equipos en la base de datos
        home_team = self._find_team_by_name(home_team_name, league)
        away_team = self._find_team_by_name(away_team_name, league)
        
        if not home_team or not away_team:
            logger.debug(f"Teams not found for JSON match: {home_team_name} vs {away_team_name}")
            return False
        
        # Parsear fecha
        fecha_str = partido_data.get('FECHA', '')
        hora_str = partido_data.get('HORA', '')
        
        if not fecha_str:
            return False
        
        try:
            if hora_str:
                match_datetime = datetime.strptime(f"{fecha_str} {hora_str}", "%d/%m/%Y %H:%M")
            else:
                match_datetime = datetime.strptime(fecha_str, "%d/%m/%Y")
            
            match_datetime = timezone.make_aware(match_datetime)
            
        except ValueError:
            return False
        
        # VERIFICAR DUPLICADOS: Buscar si ya existe un partido con los mismos equipos y fecha
        from datetime import timedelta
        date_start = match_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
        date_end = date_start + timedelta(days=1)
        
        existing_match = Match.objects.filter(
            league=league,
            home_team=home_team,
            away_team=away_team,
            match_date__gte=date_start,
            match_date__lt=date_end,
            is_friendly=False  # Solo verificar partidos oficiales
        ).first()
        
        if existing_match:
            logger.info(f"Match already exists (by teams and date): {home_team.name} vs {away_team.name} on {match_datetime.date()}")
            return False
        
        # Validar resultado antes de crear nuevo partido
        home_score = partido_data.get('RESULTADO_LOCAL')
        away_score = partido_data.get('RESULTADO_VISITANTE')
        
        if home_score is not None and away_score is not None:
            if not validate_volleyball_score(home_score, away_score, league):
                logger.warning(f"Resultado inválido para nuevo partido: {home_team.name} vs {away_team.name} - {home_score}-{away_score}")
                # No crear partido con resultado inválido
                return False
        
        # Crear partido
        match = Match.objects.create(
            league=league,
            home_team=home_team,
            away_team=away_team,
            match_date=match_datetime,
            home_score=home_score,
            away_score=away_score,
            venue=(partido_data.get('Campo') or '').strip(),
            city=(partido_data.get('Municipio') or '').strip(),
            referee1=(partido_data.get('arbitro1') or '').strip(),
            referee2=(partido_data.get('arbitro2') or '').strip(),
            scorer=(partido_data.get('anotador') or '').strip(),
            timekeeper=(partido_data.get('cronometrador') or '').strip(),
            delegate=(partido_data.get('delegado') or '').strip(),
            field_address=(partido_data.get('Direccion_Campo') or '').strip(),
            federation_club_local_id=str(partido_data.get('ID_CLUB_LOCAL', '')),
            federation_club_away_id=str(partido_data.get('ID_CLUB_VISITANTE', '')),
            federation_id=json_match_id,
            acta_html=self._build_acta_url(partido_data),
            status='scheduled'
        )
        
        logger.info(f"Created new match from JSON: {match}")
        return True
    
    def _find_team_by_name(self, team_name: str, league: League) -> Optional[Team]:
        """Busca un equipo por nombre en la liga específica"""
        # Obtener las categorías de la liga
        league_categories = league.categories.all()

        # Buscar por nombre exacto en cualquiera de las categorías de la liga
        team = Team.objects.filter(name=team_name, category__in=league_categories).first()
        if team:
            return team

        # Buscar por similitud
        normalized_name = self._normalize_team_name(team_name)
        for team in Team.objects.filter(category__in=league_categories):
            if self._normalize_team_name(team.name) == normalized_name:
                return team

        return None
    
    def _normalize_team_name(self, name: str) -> str:
        """Normaliza nombres de equipos para búsqueda flexible"""
        if not name:
            return ""
        # Convertir a mayúsculas y quitar acentos
        import unidecode
        normalized = unidecode.unidecode(name.upper())
        # Quitar caracteres especiales y espacios extra
        normalized = ''.join(c for c in normalized if c.isalnum() or c.isspace())
        normalized = ' '.join(normalized.split())
        return normalized
    
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