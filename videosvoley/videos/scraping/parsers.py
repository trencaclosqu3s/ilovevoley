"""Parsers de HTML y JSON para datos de la federación."""

from datetime import datetime
import json
import logging
import re
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup
from django.utils import timezone

from ..models import League
from .base import BaseParser, ScrapingError

logger = logging.getLogger(__name__)


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




__all__ = [
    'StandingsParser',
    'MatchesParser',
    'CalendarParser',
    'JSONMatchesParser',
    'JSONUnifiedParser',
]
