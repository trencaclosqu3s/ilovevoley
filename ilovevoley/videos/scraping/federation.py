"""Scraper principal para la federación."""

from datetime import datetime, timedelta
import json
import logging
import re
import string
import time
from typing import Any, Dict, List, Optional

from django.db import models, transaction
from django.utils import timezone
import requests
from unidecode import unidecode

from ilovevoley.competitions.services.delta_detector import detect_and_record_match_changes
from ..models import League, Match, ScrapingEndpoint, Standing, Team
from .base import ScrapingError, validate_volleyball_score
from .parsers import (
    CalendarParser,
    JSONUnifiedParser,
    MatchesParser,
    StandingsParser,
)

logger = logging.getLogger(__name__)



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
    
    def _fetch_json_with_retry(self, json_url: str, max_attempts: int = 3) -> requests.Response:
        """
        Realiza un GET reintentando ante timeouts y errores 5xx transitorios
        (p.ej. 522 de Cloudflare cuando el origen no responde a tiempo).
        """
        retryable_statuses = {500, 502, 503, 504, 522, 524}
        last_error = None

        for attempt in range(max_attempts):
            try:
                response = requests.get(json_url, timeout=60)
                if response.status_code in retryable_statuses:
                    raise requests.exceptions.HTTPError(
                        f"{response.status_code} Server Error (transitorio) para url: {json_url}",
                        response=response,
                    )
                return response
            except (requests.exceptions.ReadTimeout, requests.exceptions.HTTPError) as e:
                last_error = e
                if attempt < max_attempts - 1:
                    wait = 10 * (attempt + 1)
                    logger.warning(
                        f"Intento {attempt + 1}/{max_attempts} fallido para {json_url} ({e}), "
                        f"reintentando en {wait}s..."
                    )
                    time.sleep(wait)
                else:
                    raise last_error

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
            response = self._fetch_json_with_retry(json_url)
            json_data = json.loads(response.text)

            # Obtener IDs de ligas que tenemos en la base de datos (si se requiere filtrado)
            db_league_ids = set()
            if filter_by_db_leagues:
                db_league_ids = set(League.objects.filter(federation_id__isnull=False).values_list('federation_id', flat=True))
                logger.info(f"Filtrando por {len(db_league_ids)} ligas en BD: {sorted(db_league_ids)}")
            
            # Crear mapeo de grupo_id a league para procesamiento eficiente
            group_league_map = {}
            if filter_by_db_leagues:
                group_league_map = {
                    league.federation_id: league
                    for league in League.objects.filter(federation_id__in=db_league_ids, is_active=True)
                }
            
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
                    league_category = league.categories.first()
                    if not home_team and league_category:
                        home_team = self._find_or_create_team_by_name(
                            match_data['home_team'], league, league_category
                        )
                    if not away_team and league_category:
                        away_team = self._find_or_create_team_by_name(
                            match_data['away_team'], league, league_category
                        )
                    if not home_team or not away_team:
                        logger.warning(f'No se pudieron encontrar ni crear equipos: {match_data["home_team"]} vs {match_data["away_team"]}')
                        continue
                
                # Buscar partido existente
                # 1. Prioridad: Buscar por federation_id acotando por liga (incluye withdrawn)
                fed_id = str(match_data.get('federation_id') or '').strip()
                match = None
                if fed_id:
                    match = Match.all_objects.filter(federation_id=fed_id, league=league).first()

                # 2. Fallback: Buscar por equipos y fecha en el mismo día dentro de la liga (para partidos creados sin ID)
                if not match:
                    match_dt = match_data['match_date']
                    date_start = match_dt.replace(hour=0, minute=0, second=0, microsecond=0)
                    date_end = date_start + timedelta(days=1)
                    match = Match.all_objects.filter(
                        league=league,
                        home_team=home_team,
                        away_team=away_team,
                        match_date__gte=date_start,
                        match_date__lt=date_end,
                        is_friendly=False
                    ).first()

                if match:
                    # Un partido withdrawn solo se reactiva cuando sus equipos vuelven a
                    # aparecer en la federación (is_active la gestiona update_teams). El JSON
                    # sirve los partidos como 'scheduled', así que por sí solo no debe
                    # resucitar un partido retirado: era la otra mitad del vaivén (#235).
                    # En cada scrape detect_withdrawn_teams() corre al final, después de
                    # update_matches(), así que is_active refleja el estado de esta ejecución.
                    # Si falta alguno de los dos equipos (dato incompleto), se mantiene
                    # withdrawn en lugar de reactivar a ciegas.
                    incoming_status = match_data['status']
                    teams_still_active = bool(
                        home_team and away_team and home_team.is_active and away_team.is_active
                    )
                    if match.status == 'withdrawn' and not teams_still_active:
                        incoming_status = 'withdrawn'

                    # Detectar y registrar modificaciones federativas
                    detect_and_record_match_changes(match, {**match_data, 'status': incoming_status})

                    # Actualizar partido existente
                    match.home_score = match_data['home_score']

                    match.away_score = match_data['away_score']
                    match.status = incoming_status
                    match.venue = match_data.get('venue', '')
                    match.city = match_data.get('city', '')
                    match.referee1 = match_data.get('referee1', '')
                    match.referee2 = match_data.get('referee2', '')
                    match.scorer = match_data.get('scorer', '')
                    match.timekeeper = match_data.get('timekeeper', '')
                    match.delegate = match_data.get('delegate', '')
                    match.field_address = match_data.get('field_address', '')
                    if fed_id:
                        match.federation_id = fed_id
                    match.match_date = match_data['match_date']
                    match.acta_html = match_data.get('acta_html', '')
                    if home_team and match.home_team_id != home_team.id:
                        match.home_team = home_team
                    if away_team and match.away_team_id != away_team.id:
                        match.away_team = away_team
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
                        federation_id=fed_id or None,
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
        """Actualiza o crea los equipos vistos en la federación.

        La detección de retiradas no se hace aquí (un scrape parcial no es una foto
        completa de la liga): ver ``detect_withdrawn_teams()``.
        """
        team_objects = {}
        
        # Procesar equipos encontrados en el scraping
        for team_data in teams_data:
            # Buscar equipo existente por federation_id primero
            team = Team.objects.filter(federation_id=team_data['federation_id']).first()
            
            if not team:
                # Si no existe por federation_id, buscar por nombre normalizado para evitar duplicados
                from ilovevoley.videos.utils import find_duplicate_team_by_name, find_similar_team_by_name
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
                    # Intentar búsqueda difusa para typos (ej: LUCI'S WORD vs LUCI'S WORK)
                    similar_team, score = find_similar_team_by_name(
                        team_data['name'],
                        category=league_category,
                        threshold=0.9  # Alta similitud requerida
                    )
                    
                    if similar_team:
                        logger.info(f"Found similar team ({score:.2f}): '{team_data['name']}' -> '{similar_team.name}'")
                        similar_team.federation_id = team_data['federation_id']
                        similar_team.is_active = True
                        similar_team.save()
                        team = similar_team
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
                from ilovevoley.videos.utils import normalize_team_name
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
        
        return team_objects
    
    @transaction.atomic
    def detect_withdrawn_teams(self, current_federation_ids) -> List[Team]:
        """Marca como inactivos los equipos de la liga que ya no aparecen en la federación.

        Se evalúa una sola vez por ejecución con el conjunto COMPLETO de equipos vistos
        entre todos los endpoints o jornadas. Detectar la retirada por endpoint parcial
        desactivaba equipos que simplemente no jugaban esa jornada, y esa alternancia
        provocaba el vaivén withdrawn/scheduled y los avisos repetidos por el mismo
        partido (#235).

        Equipos y partidos se actualizan en la misma transacción para no dejar un equipo
        inactivo con sus partidos aún programados si algo falla.

        Args:
            current_federation_ids: federation_ids vistos en toda la ejecución.

        Returns:
            Lista de equipos marcados como inactivos.
        """
        if not current_federation_ids:
            return []

        existing_teams_in_league = Team.objects.filter(
            models.Q(home_matches__league=self.league) | models.Q(away_matches__league=self.league)
        ).filter(is_active=True).distinct()

        withdrawn_teams = list(
            existing_teams_in_league.exclude(federation_id__in=current_federation_ids)
        )

        if withdrawn_teams:
            Team.objects.filter(pk__in=[t.pk for t in withdrawn_teams]).update(is_active=False)
            for team in withdrawn_teams:
                logger.warning(
                    f"Team marked as inactive (withdrawn): {team.name} "
                    f"(federation_id: {team.federation_id}) - no longer appears in {self.league.name}"
                )
            logger.info(f"Detected {len(withdrawn_teams)} withdrawn teams in {self.league.name}")
            self._mark_withdrawn_matches()

        return withdrawn_teams
    
    def _normalize_team_name(self, name: str) -> str:
        """Normaliza nombres de equipos para comparación"""
        # Remover acentos y convertir a mayúsculas
        normalized = unidecode(name).upper()
        # Remover espacios extra y caracteres especiales
        normalized = ' '.join(normalized.split())
        return normalized
    
    def _calculate_won_lost_from_matches(self, team) -> Dict[str, int]:
        """
        Calcula partidos ganados y perdidos desde los partidos finalizados.
        Especialmente importante para formato alevín, donde la tabla de la federación
        puede tener estructura distinta (ej. todos con 0 perdidos).
        """
        matches = Match.objects.filter(
            league=self.league,
            status='finished'
        ).filter(
            models.Q(home_team=team) | models.Q(away_team=team)
        )
        won = 0
        lost = 0
        for match in matches:
            if match.home_score is None or match.away_score is None:
                continue
            is_home = (match.home_team == team)
            sets_won = match.home_score if is_home else match.away_score
            sets_lost = match.away_score if is_home else match.home_score
            if sets_won > sets_lost:
                won += 1
            elif sets_lost > sets_won:
                lost += 1
        return {'won': won, 'lost': lost}

    def _calculate_team_stats_from_matches(self, team) -> Dict[str, int]:
        """
        Calcula estadísticas detalladas (breakdown de resultados) desde los partidos guardados.
        Esto es necesario porque la tabla de la federación agrupa G3 (3-0 y 3-1) y P0 (0-3 y 1-3),
        haciendo imposible distinguir estos resultados solo con la tabla.
        Para formato alevín (3 sets, 2-1/1-2/3-0/0-3) estos contadores no aplican; en la vista
        se ocultan las estadísticas detalladas para ligas alevín.
        """
        stats = {
            'wins_3_0': 0, 'wins_3_1': 0, 'wins_3_2': 0,
            'losses_2_3': 0, 'losses_1_3': 0, 'losses_0_3': 0
        }
        
        # Ligas alevín: no usamos el desglose 3-0/3-1/... (siempre 3 sets, 2-1 o 1-2)
        if self.league.match_format == 'alevin_balear':
            return stats

        # Obtener todos los partidos finalizados de este equipo en esta liga
        matches = Match.objects.filter(
            league=self.league,
            status='finished'
        ).filter(
            models.Q(home_team=team) | models.Q(away_team=team)
        )
        
        for match in matches:
            # Asegurarse de tener resultados válidos
            if match.home_score is None or match.away_score is None:
                continue
                
            is_home = (match.home_team == team)
            sets_won = match.home_score if is_home else match.away_score
            sets_lost = match.away_score if is_home else match.home_score
            
            # Clasificar resultado (formato estándar 5 sets)
            if sets_won == 3:
                if sets_lost == 0: stats['wins_3_0'] += 1
                elif sets_lost == 1: stats['wins_3_1'] += 1
                elif sets_lost == 2: stats['wins_3_2'] += 1
            elif sets_lost == 3:
                if sets_won == 2: stats['losses_2_3'] += 1
                elif sets_won == 1: stats['losses_1_3'] += 1
                elif sets_won == 0: stats['losses_0_3'] += 1
                
        return stats

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
            
            # Calcular estadísticas detalladas desde los partidos reales
            # Esto corrige el problema de interpretación de G3/G2/etc de la federación
            detailed_stats = self._calculate_team_stats_from_matches(team)
            
            # Solo si tenemos partidos para calcular (para no poner ceros si no tenemos partidos scrapeados aún)
            matches_exist = Match.objects.filter(
                league=self.league,
                status='finished'
            ).filter(
                models.Q(home_team=team) | models.Q(away_team=team)
            ).exists()
            
            if matches_exist:
                standing_data.update(detailed_stats)
                # Formato alevín: la tabla de la federación suele tener estructura distinta
                # (ej. todos con 0 perdidos). Calculamos G/P desde los partidos reales.
                if self.league.match_format == 'alevin_balear':
                    won_lost = self._calculate_won_lost_from_matches(team)
                    standing_data['won'] = won_lost['won']
                    standing_data['lost'] = won_lost['lost']
            
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
                existing_match = Match.all_objects.filter(
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
                            # Detectar y registrar modificaciones federativas
                            detect_and_record_match_changes(existing_match, match_data)
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
                existing_match = Match.all_objects.filter(
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

                existing_match = Match.all_objects.filter(
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
                # Detectar y registrar modificaciones federativas
                detect_and_record_match_changes(existing_match, match_data)

                # Si el partido estaba withdrawn pero ahora los equipos son activos, reactivarlo

                if existing_match.status == 'withdrawn' and home_team.is_active and away_team.is_active:
                    existing_match.status = 'scheduled'
                    existing_match.save()
                    logger.info(f"Reactivated withdrawn match: {home_team.name} vs {away_team.name}")

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
                        # Actualizar si el datetime ha cambiado (cambio de día, hora o ambos)
                        if new_value != current_value:
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
        withdrawn_matches = list(
            Match.objects.filter(
                league=self.league,
                status__in=['scheduled', 'postponed'],  # Solo marcar partidos que aún no han comenzado
                is_friendly=False  # No marcar amistosos como retirados
            ).filter(
                models.Q(home_team__is_active=False) | models.Q(away_team__is_active=False)
            ).select_related('home_team', 'away_team')
        )

        if not withdrawn_matches:
            return

        Match.objects.filter(
            pk__in=[m.pk for m in withdrawn_matches]
        ).update(status='withdrawn')

        for match in withdrawn_matches:
            # select_related recarga los equipos desde BD tras el bulk_update, así que
            # is_active ya refleja el estado nuevo.
            inactive_teams = [
                team.name
                for team in (match.home_team, match.away_team)
                if not team.is_active
            ]
            logger.warning(
                f"Match marked as withdrawn: {match.home_team.name} vs {match.away_team.name} "
                f"on {match.match_date.strftime('%d/%m/%Y')} - inactive teams: {', '.join(inactive_teams)}"
            )

        logger.info(f"Marked {len(withdrawn_matches)} matches as withdrawn in {self.league.name}")
    
    def _is_empty_value(self, value) -> bool:
        """Determina si un valor está vacío o es None"""
        if value is None:
            return True
        if isinstance(value, str) and value.strip() == '':
            return True
        return False
    
    def _find_similar_team(self, team_name: str) -> Optional[Team]:
        """Busca equipos similares en la base de datos, prefiriendo la categoría de la liga"""
        normalized_name = self._normalize_team_name(team_name)

        # Primero buscar por nombre normalizado en la categoría de la liga
        league_categories = self.league.categories.all()
        for team in Team.objects.filter(category__in=league_categories):
            if self._normalize_team_name(team.name) == normalized_name:
                return team

        # Fallback: buscar por nombre normalizado en todas las categorías
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
        
        # Retiradas: evaluar una sola vez con la unión de equipos de todas las jornadas
        self.detect_withdrawn_teams(
            {team.federation_id for team in all_teams.values() if team.federation_id}
        )

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
            response = self._fetch_json_with_retry(json_url)

            # Parsear JSON
            json_data = json.loads(response.text)
            
            enriched_count = 0
            new_matches_count = 0
            processed_groups = 0
            skipped_groups = 0
            
            # Recopilar todos los partidos de grupos que tenemos en la BD
            all_matches = []
            group_league_map = {}  # Mapeo grupo_id -> league
            
            # Crear mapeo de grupo_id a league en una sola query
            group_league_map = {
                league.federation_id: league
                for league in League.objects.filter(federation_id__in=db_league_ids, is_active=True)
            }
            
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
                match_exists = Match.all_objects.filter(federation_id=json_match_id).exists() if json_match_id else False
                
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
        
        # Primero intentar buscar por federation_id del JSON (incluye withdrawn)
        try:
            match = Match.all_objects.get(federation_id=json_match_id)
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
                        from ilovevoley.videos.models import Club
                        
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
                            from ilovevoley.videos.utils import normalize_team_name as normalize_team_name_util
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
            
        # Verificar si ya existe un partido con este federation_id (incluye withdrawn)
        if Match.all_objects.filter(federation_id=json_match_id).exists():
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
        
        existing_match = Match.all_objects.filter(
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

    def _find_or_create_team_by_name(self, team_name: str, league: League, league_category) -> Team:
        """
        Busca un equipo por nombre difuso antes de crear uno nuevo, para no fragmentar
        el mismo equipo real en varias filas cuando cambia de liga/fase (y por tanto de
        federation_id) y el nombre exacto no coincide.
        """
        from ilovevoley.videos.utils import find_duplicate_team_by_name, find_similar_team_by_name

        team = find_duplicate_team_by_name(team_name, category=league_category)
        if not team:
            team, score = find_similar_team_by_name(team_name, category=league_category, threshold=0.9)

        if team:
            logger.info(f"Equipo reutilizado por nombre: '{team_name}' -> '{team.name}' (ID: {team.id})")
            return team

        fed_id = f"{league.federation_id}_{team_name.replace(' ', '_').lower()}"
        team = Team.objects.create(
            name=team_name, federation_id=fed_id, category=league_category, is_active=True
        )
        logger.info(f"Equipo creado automáticamente: {team.name} para liga {league.name}")
        return team

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
        
        available_keys = set(kwargs.keys()) | {'league_id'}
        for endpoint in self.league.endpoints.filter(is_active=True):
            required_keys = {
                field_name
                for _, field_name, _, _ in string.Formatter().parse(endpoint.url_pattern)
                if field_name
            }
            missing = required_keys - available_keys
            if missing:
                logger.info(f"Skipping endpoint {endpoint}: missing required params {missing}")
                continue
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
                if 'matches' in data:
                    self.update_matches(data['matches'], all_teams)
                    
            except Exception as e:
                logger.error(f"Error scraping endpoint {endpoint}: {e}")
                results[endpoint.endpoint_type] = {'error': str(e)}

        # Retiradas: evaluar una sola vez con la unión de equipos de todos los endpoints
        self.detect_withdrawn_teams(
            {team.federation_id for team in all_teams.values() if team.federation_id}
        )

        return results




__all__ = [
    'FederationScraper',
]
