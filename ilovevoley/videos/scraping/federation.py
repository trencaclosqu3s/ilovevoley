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

from ilovevoley.competitions.services.delta_detector import (
    detect_and_record_match_changes,
    notify_match_result_after_save,
)
from ..models import League, Match, ScrapingEndpoint, Standing, Team
from .base import (
    ScrapingError,
    build_acta_url,
    is_penalty_result,
    validate_volleyball_score,
)
from .parsers import (
    CalendarParser,
    JSONUnifiedParser,
    MatchesParser,
    StandingsParser,
)

logger = logging.getLogger(__name__)

# Jornadas a cada lado de la actual en las que se busca un partido que no está en ella.
MAX_ROUND_DISTANCE = 2
MAX_LEAGUE_ROUNDS = 60  # tope de seguridad al recorrer una liga entera



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
        self._new_identity_candidates = []
    
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

    @staticmethod
    def _parse_json_response(response: requests.Response) -> Any:
        """Parsea el JSON incluyendo en el error el cuerpo recibido: la federación responde a veces con texto plano (#463)."""
        try:
            return json.loads(response.text)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Respuesta no JSON ({response.status_code}) de {response.url}: {response.text[:200]!r}"
            ) from e

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
    
    def _fetch_round_map(self, league: League, needed: Optional[set] = None, delay: float = 0) -> Dict[tuple, int]:
        """
        Devuelve {(club_local_id, club_visitante_id): jornada} para los pares de ``needed``.
        Sin ``needed`` recorre todas las jornadas de la liga (backfill), con ``delay``
        segundos entre peticiones.

        El JSON unificado no trae jornada ni es el calendario completo (solo una ventana
        de partidos próximos o recientes), pero el HTML de resultados sí: lleva la
        jornada y el id de club de cada equipo en la URL del escudo. Sin ``jor`` devuelve
        la jornada actual; los pares que no estén ahí (adelantados, aplazados, resultados
        de la jornada anterior) se buscan en las contiguas, hasta ``MAX_ROUND_DISTANCE``.
        En una liga a doble vuelta el par (local, visitante) es único; si un club tuviera
        dos equipos en el mismo grupo se pisaría y habría que desempatar por fecha.
        Un fallo de red devuelve lo recogido hasta ese momento: la jornada es un
        enriquecimiento y no debe impedir importar los partidos.
        """
        url = f'https://www.voleibolib.net/JSON/get_resultados.asp?id={league.federation_id}'
        round_map: Dict[tuple, int] = {}

        def fetch(round_number=None):
            suffix = f'&jor={round_number}' if round_number else ''
            html = self._fetch_json_with_retry(url + suffix).text
            header = re.search(r'<h3>JORNADA (\d+)', html)
            # Fuera de rango el servidor devuelve la jornada 1, no un error.
            if not header or (round_number and int(header.group(1)) != round_number):
                return None
            current_round_num = int(header.group(1))
            try:
                from ilovevoley.competitions.services.acta_photo import process_acta_photos_from_html
                process_acta_photos_from_html(html, league=league, round_number=current_round_num)
            except Exception as e:
                logger.warning(f'Error procesando fotos de acta en {league.name}: {e}')
            for block in html.split("class='info_partido")[1:]:
                clubs = re.findall(r'clubes/(\d+)mini', block)
                if len(clubs) >= 2:
                    round_map[(clubs[0], clubs[1])] = current_round_num
            return current_round_num

        try:
            if needed is None:
                for round_number in range(1, MAX_LEAGUE_ROUNDS + 1):
                    if fetch(round_number) is None:
                        break
                    time.sleep(delay)
                return round_map
            current = fetch()
            if current:
                for distance in range(1, MAX_ROUND_DISTANCE + 1):
                    if needed <= round_map.keys():
                        break
                    for candidate in (current - distance, current + distance):
                        if candidate >= 1:
                            fetch(candidate)
        except Exception as e:
            logger.warning(f'No se pudo obtener el número de jornada de {league.name}: {e}')
        return round_map

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
            json_data = self._parse_json_response(response)

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
                                        league, partidos, categoria_name, grupo_id, op_type,
                                        round_map=self._fetch_round_map(league, {
                                            (str(p.get('ID_CLUB_LOCAL', '')), str(p.get('ID_CLUB_VISITANTE', '')))
                                            for p in partidos
                                        }),
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
    
    def _process_json_matches_unified(self, league, partidos_data, categoria_name, grupo_id, op_type, round_map=None):
        """Procesa los partidos encontrados en un grupo específico del JSON usando el parser unificado"""
        from unidecode import unidecode
        from datetime import datetime
        from django.utils import timezone
        
        from ilovevoley.teams.identity import notify_new_identity_candidates

        matches_created = 0
        matches_updated = 0
        self._new_identity_candidates = []
        # Partidos que este scrape confirma como vigentes: la federación es la
        # autoridad de qué fila del calendario vive y cuál es espejo (#485).
        confirmed_pks = set()

        for partido_data in partidos_data:
            try:
                # Usar el parser unificado para procesar el partido
                parser = JSONUnifiedParser(league, op_type=op_type)
                match_data = parser._parse_single_json_match(partido_data, grupo_id, categoria_name)
                
                if not match_data:
                    continue

                round_number = (round_map or {}).get(
                    (match_data['federation_club_local_id'], match_data['federation_club_away_id'])
                )

                # Buscar equipos
                home_team = self._find_team_by_name(match_data['home_team'], league)
                away_team = self._find_team_by_name(match_data['away_team'], league)
                
                if not home_team or not away_team:
                    league_category = league.categories.first()
                    if not home_team and league_category:
                        home_team = self._find_or_create_team_by_name(
                            match_data['home_team'], league, league_category,
                            match_data.get('federation_club_local_id', ''),
                            sponsor_name=match_data.get('home_sponsor_name', ''),
                        )
                    if not away_team and league_category:
                        away_team = self._find_or_create_team_by_name(
                            match_data['away_team'], league, league_category,
                            match_data.get('federation_club_away_id', ''),
                            sponsor_name=match_data.get('away_sponsor_name', ''),
                        )
                    if not home_team or not away_team:
                        logger.warning(f'No se pudieron encontrar ni crear equipos: {match_data["home_team"]} vs {match_data["away_team"]}')
                        continue
                
                self._sync_sponsor_name(home_team, match_data['home_team'], match_data.get('home_sponsor_name', ''))
                self._sync_sponsor_name(away_team, match_data['away_team'], match_data.get('away_sponsor_name', ''))

                # Buscar partido existente
                # 1. Prioridad: Buscar por federation_id acotando por liga (incluye withdrawn)
                fed_id = str(match_data.get('federation_id') or '').strip()
                match = None
                if fed_id:
                    match = Match.all_objects.filter(federation_id=fed_id, league=league).first()

                # 2. Fallback: Buscar por equipos y fecha en el mismo día dentro de la liga,
                # también con local/visitante invertidos (#485).
                if not match:
                    match = self._find_calendar_match(
                        league, home_team, away_team, match_data['match_date']
                    )

                if match:
                    confirmed_pks.add(match.pk)
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
                    already_finished = self._result_already_published(match)
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
                    match.federation_comment = (match_data.get('comentario') or '')
                    if fed_id:
                        match.federation_id = fed_id
                    match.match_date = match_data['match_date']
                    if round_number:
                        match.round_number = round_number
                    incoming_acta = build_acta_url(
                        match_data.get('acta_html', ''),
                        fed_id or match.federation_id,
                    )
                    if incoming_acta:
                        match.acta_html = incoming_acta
                    if home_team and match.home_team_id != home_team.id:
                        match.home_team = home_team
                    if away_team and match.away_team_id != away_team.id:
                        match.away_team = away_team
                    match.save()
                    notify_match_result_after_save(match, already_finished)
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
                        acta_html=build_acta_url(match_data.get('acta_html', ''), fed_id),
                        federation_comment=(match_data.get('comentario') or ''),
                        round_number=round_number or 1
                    )
                    matches_created += 1
                    
                    logger.debug(f'Creado: {home_team.name} {match.home_score}-{match.away_score} {away_team.name}')
                    
            except Exception as e:
                logger.error(f'Error procesando partido {partido_data.get("ELOCAL", "Unknown")} vs {partido_data.get("EVISITANTE", "Unknown")}: {str(e)}')
                continue

        if self._new_identity_candidates:
            notify_new_identity_candidates(self._new_identity_candidates)

        self._deduplicate_mirror_matches(league, confirmed_pks)

        return matches_created, matches_updated
    
    @transaction.atomic
    def update_teams(self, teams_data: List[Dict[str, Any]]) -> Dict[str, Team]:
        """Actualiza o crea los equipos vistos en la federación.

        Un ``federation_id`` nuevo crea siempre una aparición ``Team`` nueva; la
        continuidad entre temporadas (y entre fases/grupos de la misma temporada)
        va por ``TeamIdentity`` (#428), no reescribiendo el ``federation_id`` de
        filas anteriores ni reutilizando por nombre (eso mezclaba Portol Rojo/Negro).

        Los consumidores que aún miran un solo ``Team`` por temporada no agregan
        por identidad: es deuda conocida; la identidad es el hilo, no un merge de PK.

        La detección de retiradas no se hace aquí (un scrape parcial no es una foto
        completa de la liga): ver ``detect_withdrawn_teams()``.
        """
        from ilovevoley.teams.identity import notify_new_identity_candidates, resolve_team_identity
        from ilovevoley.videos.utils import normalize_team_name

        self._new_identity_candidates = []
        team_objects = {}

        for team_data in teams_data:
            club_fed_id = team_data.get('federation_club_id', '')
            sponsor_name = (team_data.get('sponsor_name') or '').strip()
            # PAT igual al nombre base = sin patrocinio (misma regla que _sync_sponsor_name)
            if sponsor_name == (team_data.get('name') or '').strip():
                sponsor_name = ''
            league_category = self.league.categories.first()
            team = Team.objects.filter(federation_id=team_data['federation_id']).first()
            created = False

            if not team:
                team = Team.objects.create(
                    name=team_data['name'],
                    federation_id=team_data['federation_id'],
                    category=league_category,
                    sponsor_name=sponsor_name,
                    is_active=True,
                )
                created = True

            updated = False
            if not created and team.name != team_data['name']:
                if normalize_team_name(team.name) != normalize_team_name(team_data['name']):
                    team.name = team_data['name']
                    updated = True
                else:
                    logger.info(
                        f"Team name variation detected but keeping original: "
                        f"'{team.name}' vs '{team_data['name']}'"
                    )

            if sponsor_name and team.sponsor_name != sponsor_name:
                team.sponsor_name = sponsor_name
                updated = True

            if league_category and team.category != league_category:
                team.category = league_category
                updated = True
                logger.info(f"Assigned category '{league_category}' to team: {team.name}")

            if self._assign_federation_club(team, club_fed_id):
                updated = True

            if not team.is_active:
                team.is_active = True
                updated = True
                logger.info(f"Reactivated team: {team.name} - now appears in federation data again")

            if updated:
                team.save()

            if created or team.identity_id is None:
                _, candidate = resolve_team_identity(team, sponsor_name=sponsor_name or team.sponsor_name)
                if candidate:
                    self._new_identity_candidates.append(candidate)

            team_objects[team_data['name']] = team
            team_objects[self._normalize_team_name(team_data['name'])] = team

            if created:
                logger.info(f"Created new team: {team.name} with category: {league_category}")

        if self._new_identity_candidates:
            notify_new_identity_candidates(self._new_identity_candidates)

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

        # Partidos que este scrape confirma como vigentes: la federación es la
        # autoridad de qué fila del calendario vive y cuál es espejo (#485).
        confirmed_pks = set()

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
                if not home_team:
                    home_team = self._find_league_team_by_club(
                        home_team_name, match_data.get('federation_club_local_id', ''))
                if not away_team:
                    away_team = self._find_league_team_by_club(
                        away_team_name, match_data.get('federation_club_away_id', ''))

                if self.league.is_historical and (not home_team or not away_team):
                    # La clasificación de una temporada pasada omite equipos retirados:
                    # sin su Team el partido jugado se perdería del H2H.
                    category = self.league.categories.first()
                    if category and not home_team:
                        home_team = self._find_or_create_team_by_name(
                            home_team_name, self.league, category,
                            match_data.get('federation_club_local_id', ''))
                    if category and not away_team:
                        away_team = self._find_or_create_team_by_name(
                            away_team_name, self.league, category,
                            match_data.get('federation_club_away_id', ''))

                if not home_team or not away_team:
                    logger.error(f"Could not match teams: {home_team_name} vs {away_team_name}")
                    continue

            # El id de club del escudo sitúa también al equipo encontrado por nombre (#464)
            for team, club_key in ((home_team, 'federation_club_local_id'), (away_team, 'federation_club_away_id')):
                if self._assign_federation_club(team, match_data.get(club_key, '')):
                    team.save(update_fields=['club'])

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
                    confirmed_pks.add(existing_match.pk)
                    # Validar resultado antes de actualizar
                    home_score = match_data.get('home_score')
                    away_score = match_data.get('away_score')
                    
                    if home_score is not None and away_score is not None:
                        if validate_volleyball_score(home_score, away_score, self.league):
                            # Detectar y registrar modificaciones federativas
                            already_finished = self._result_already_published(existing_match)
                            detect_and_record_match_changes(existing_match, match_data)
                            # Solo actualizar resultado y estado
                            existing_match.home_score = home_score

                            existing_match.away_score = away_score
                            existing_match.status = match_data.get('status', 'finished')
                            self._apply_set_scores(existing_match, match_data)
                            existing_match.save()
                            notify_match_result_after_save(existing_match, already_finished)
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

            # PRIORIDAD 2: Si no se encontró por jornada, buscar por fecha (fallback),
            # también con local/visitante invertidos si la federación los cambió (#485)
            if not existing_match and match_date:
                existing_match = self._find_calendar_match(
                    self.league, home_team, away_team, match_date
                )
                
                if existing_match:
                    logger.info(f"Found existing match by date: {home_team.name} vs {away_team.name} on {match_date.date()}")
            
            # Crear o actualizar el partido con merge inteligente
            if existing_match:
                confirmed_pks.add(existing_match.pk)
                # Detectar y registrar modificaciones federativas
                already_finished = self._result_already_published(existing_match)
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

                # El match_data ya no lleva los equipos (se pop-ean arriba): si el
                # partido recuperado estaba con localía invertida (#485), reasignarlos.
                if home_team and existing_match.home_team_id != home_team.id:
                    existing_match.home_team = home_team
                    updated_fields.append('home_team')
                if away_team and existing_match.away_team_id != away_team.id:
                    existing_match.away_team = away_team
                    updated_fields.append('away_team')

                if self._apply_set_scores(existing_match, match_data):
                    updated_fields.append('set_scores')

                for key, new_value in match_data.items():
                    # set_scores se vuelca en _apply_set_scores, que no pisa lo existente.
                    if key == 'set_scores':
                        continue
                    if key == 'acta_html':
                        if not new_value:
                            continue
                        new_value = build_acta_url(
                            new_value,
                            match_data.get('federation_id') or existing_match.federation_id,
                        )
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
                    notify_match_result_after_save(existing_match, already_finished)
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
                if valid_match_data.get('round_number') is None:
                    valid_match_data.pop('round_number', None)  # el JSON no la trae: default del modelo
                if valid_match_data.get('acta_html'):
                    valid_match_data['acta_html'] = build_acta_url(
                        valid_match_data['acta_html'],
                        valid_match_data.get('federation_id'),
                    )
                
                match = Match.objects.create(
                    league=self.league,
                    home_team=home_team,
                    away_team=away_team,
                    **valid_match_data
                )
                if match.set_scores and is_penalty_result(match.set_scores):
                    match.result_penalized = True
                    match.save(update_fields=['result_penalized'])
                logger.info(f"Created new match: {match}")
        
        # MARCAR PARTIDOS COMO WITHDRAWN: partidos que involucran equipos inactivos
        self._mark_withdrawn_matches()
        self._deduplicate_mirror_matches(self.league, confirmed_pks)
    
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

    def _find_calendar_match(self, league, home_team, away_team, match_date):
        """Localiza el partido del calendario que corresponde a uno del scrape.

        El empate por ``federation_id`` es la via principal (la gestiona cada
        llamador); este fallback cubre partidos en BD sin id (calendario HTML).
        Empareja por liga + dia + par de equipos, prefiriendo la fila que ya
        lleva id federativo. Si la federacion ha cambiado la localia del
        partido ya programado (#485), el par aparece invertido: se busca
        tambien visitante/local en la misma fecha, que solo puede ser el mismo
        cruce (un cruce no se juega dos veces el mismo dia).
        """
        date_start = match_date.replace(hour=0, minute=0, second=0, microsecond=0)
        date_end = date_start + timedelta(days=1)
        match = Match.all_objects.filter(
            league=league,
            home_team=home_team,
            away_team=away_team,
            match_date__gte=date_start,
            match_date__lt=date_end,
            is_friendly=False,
        ).order_by(models.F('federation_id').desc(nulls_last=True), 'pk').first()
        if match:
            return match
        # Solo crucees aun por jugar: reclamar un match finalizado con el par
        # invertido reescribiria el resultado ya publicado.
        return Match.all_objects.filter(
            league=league,
            home_team=away_team,
            away_team=home_team,
            match_date__gte=date_start,
            match_date__lt=date_end,
            is_friendly=False,
            status__in=['scheduled', 'postponed'],
        ).order_by(models.F('federation_id').desc(nulls_last=True), 'pk').first()

    def _deduplicate_mirror_matches(self, league, confirmed_pks=None):
        """Retira los duplicados en espejo dejados atrás por las dos fuentes (#485).

        Un mismo cruce no puede estar programado dos veces el mismo día. La
        federación es la autoridad: en cada scrape, el partido que se empareja
        y actualiza (sea por id, por orden de equipos o con la localía
        invertida) es el vigente; el resto de filas del mismo cruce y fecha
        quedan reflejos de ejecuciones anteriores y pasan a ``withdrawn``.

        El barrido es convergente: en una ejecución sin confirmaciones no se
        toca nada, y las filas duplicadas con id distinto entre sí quedan en
        warning para revisión manual.
        """
        if not confirmed_pks:
            return
        confirmed_pks = set(confirmed_pks)

        unfinished = list(
            Match.all_objects.filter(
                league=league,
                status__in=['scheduled', 'postponed'],
                is_friendly=False,
            ).select_related('home_team', 'away_team')
        )
        groups = {}
        for fixture in unfinished:
            if fixture.home_team_id and fixture.away_team_id and fixture.home_team_id != fixture.away_team_id:
                key = (
                    fixture.match_date.date(),
                    frozenset({fixture.home_team_id, fixture.away_team_id}),
                )
                groups.setdefault(key, []).append(fixture)

        to_withdraw = []
        for members in groups.values():
            if len(members) < 2:
                continue
            confirmed = [fixture for fixture in members if fixture.pk in confirmed_pks]
            if len(confirmed) > 1:
                logger.warning(
                    f'More than one confirmed match in {league.name} on '
                    f'{members[0].match_date:%d/%m/%Y}, skipping auto-withdraw: '
                    + ', '.join(f'#{fixture.pk}' for fixture in confirmed)
                )
                continue
            if len(confirmed) != 1:
                continue
            for fixture in members:
                if fixture.pk != confirmed[0].pk:
                    to_withdraw.append(fixture)

        if not to_withdraw:
            return

        # Re-verificar estado: un scrape concurrente pudo finalizar un cruce del
        # listado entre el snapshot y este UPDATE.
        Match.objects.filter(
            pk__in=[m.pk for m in to_withdraw],
            status__in=['scheduled', 'postponed'],
        ).update(status='withdrawn')
        for fixture in to_withdraw:
            logger.warning(
                f'Mirror duplicate withdrawn: {fixture.home_team.name} vs {fixture.away_team.name} '
                f'on {fixture.match_date:%d/%m/%Y} in {league.name} (#{fixture.pk} without '
                f'federation confirmation)'
            )

    def _is_empty_value(self, value) -> bool:
        """Determina si un valor está vacío o es None"""
        if value is None:
            return True
        if isinstance(value, str) and value.strip() == '':
            return True
        return False

    @staticmethod
    def _result_already_published(match) -> bool:
        """Estado de resultado previo al merge, para no reenviar el push.

        Se consulta antes de volcar los datos del scrape: después el merge ya ha
        sobrescrito el marcador y no hay forma de distinguir un resultado nuevo
        de uno ya publicado.
        """
        return bool(
            match.status == 'finished'
            and match.home_score is not None
            and match.away_score is not None
        )

    def _apply_set_scores(self, match, match_data) -> bool:
        """Vuelca los parciales del scraping y marca penalización si aplica.

        Nunca pisa unos parciales ya guardados (manuales o de una ejecución
        anterior): el scraper solo rellena el hueco.
        """
        changed = False
        set_scores = match_data.get('set_scores')
        if set_scores and not match.set_scores:
            match.set_scores = set_scores
            changed = True
        if match.set_scores and not match.result_penalized and is_penalty_result(match.set_scores):
            match.result_penalized = True
            changed = True
        return changed
    
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

    def _find_league_team_by_club(self, team_name: str, club_fed_id: str) -> Optional[Team]:
        """Equipo de la liga que difiere solo en el patrocinador, si es el único (#464).

        El club solo no basta: un club tiene varios equipos por liga (MAYURQA BLACK,
        Portol Rojo/Negro) y equipos antiguos sin club asignado. Se exige además que
        las palabras de un nombre estén contenidas en las del otro (patrocinador
        añadido o quitado). Un patrocinador sustituido por otro no casa: se descarta.
        El club se asigna en ``update_matches``, igual que a los encontrados por nombre.
        """
        from ilovevoley.teams.services import EMPTY_CLUB_IDS
        if club_fed_id in EMPTY_CLUB_IDS:
            return None
        words = set(self._normalize_team_name(team_name).split())
        candidates = [
            team for team in Team.objects.filter(
                models.Q(club__isnull=True) | models.Q(club__federation_id=club_fed_id),
            ).filter(
                models.Q(home_matches__league=self.league) | models.Q(away_matches__league=self.league)
            ).distinct()
            if (other := set(self._normalize_team_name(team.name).split())) <= words or words <= other
        ]
        return candidates[0] if len(candidates) == 1 else None

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
            json_data = self._parse_json_response(response)
            
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

        if 'COMENTARIO' in partido_data:
            comment = (partido_data['COMENTARIO'] or '').strip()
            if comment != match.federation_comment:
                match.federation_comment = comment
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
        acta_url = build_acta_url(partido_data.get('acta_html'), partido_data.get('ID'))
        if acta_url and (not match.acta_html or not match.acta_html.startswith(('http://', 'https://'))):
            match.acta_html = acta_url
            updated = True
            logger.debug(f"URL del acta construida: {acta_url}")
        
        if updated:
            match.save()
            logger.debug(f"Enriched match: {match}")
        
        return updated
    
    def _build_acta_url(self, partido_data: Dict) -> str:
        """Construye la URL completa del acta usando el ID del partido"""
        return build_acta_url(partido_data.get('acta_html'), partido_data.get('ID'))
    
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

        self._sync_sponsor_name(home_team, home_team_name, (partido_data.get('ELOCALPAT') or '').strip())
        self._sync_sponsor_name(away_team, away_team_name, (partido_data.get('EVISITANTEPAT') or '').strip())
        
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
            federation_comment=(partido_data.get('COMENTARIO') or '').strip(),
            status='scheduled'
        )
        
        logger.info(f"Created new match from JSON: {match}")
        return True
    
    @staticmethod
    def _sync_sponsor_name(team: Team, base_name: str, sponsor_name: str) -> None:
        """Sincroniza ``sponsor_name`` con ELOCALPAT/EVISITANTEPAT.

        PAT vacío = sin información, no se toca. PAT distinto del nombre base = patrocinio
        vigente. PAT igual al base = la federación retiró el patrocinio: se limpia un
        valor anterior (``sponsor_name == name`` es el valor por defecto y se respeta).
        """
        if not sponsor_name:
            return
        if sponsor_name != base_name:
            new_value = sponsor_name
        elif team.sponsor_name in ('', team.name, base_name):
            return
        else:
            new_value = ''
        if team.sponsor_name != new_value:
            team.sponsor_name = new_value
            team.save(update_fields=['sponsor_name'])

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

    def _find_or_create_team_by_name(self, team_name: str, league: League, league_category,
                                     club_fed_id: str = '', sponsor_name: str = '') -> Team:
        """Crea o reutiliza por ``federation_id`` sintético; la continuidad va por identidad (#428).

        Ya no reutiliza filas por nombre/similitud (confundía colores del mismo club).
        Las candidatas se acumulan en ``_new_identity_candidates`` para un solo email.
        """
        from ilovevoley.teams.identity import resolve_team_identity

        fed_id = f"{league.federation_id}_{team_name.replace(' ', '_').lower()}"
        team = Team.objects.filter(federation_id=fed_id).first()
        created = False
        sponsor = (sponsor_name or '').strip()
        if sponsor == team_name:
            sponsor = ''
        if not team:
            team = Team.objects.create(
                name=team_name,
                federation_id=fed_id,
                category=league_category,
                sponsor_name=sponsor,
                is_active=True,
            )
            created = True
            logger.info(f"Equipo creado automáticamente: {team.name} para liga {league.name}")

        if self._assign_federation_club(team, club_fed_id):
            team.save(update_fields=['club'])

        if created or team.identity_id is None:
            _, candidate = resolve_team_identity(team, sponsor_name=sponsor or team.sponsor_name)
            if candidate:
                if not hasattr(self, '_new_identity_candidates') or self._new_identity_candidates is None:
                    self._new_identity_candidates = []
                self._new_identity_candidates.append(candidate)
        return team

    @staticmethod
    def _is_other_club(team: Team, club_fed_id: str) -> bool:
        """El equipo encontrado por nombre es de otro club según la federación (#380)."""
        from ilovevoley.teams.services import EMPTY_CLUB_IDS
        if club_fed_id in EMPTY_CLUB_IDS or team.club_id is None:
            return False
        return team.club.federation_id != club_fed_id

    @staticmethod
    def _assign_federation_club(team: Team, club_fed_id: str) -> bool:
        """Asigna a un equipo sin club el club federativo que trae el partido.

        El id de club de voleibolib es fiable e independiente del nombre, así que un
        equipo que cambia de patrocinador (y de fila ``Team``) sigue en su club.
        """
        from ilovevoley.teams.services import EMPTY_CLUB_IDS
        from ilovevoley.teams.models import Club
        if team.club_id is not None or club_fed_id in EMPTY_CLUB_IDS:
            return False
        team.club = Club.objects.filter(federation_id=club_fed_id).first()
        return team.club is not None

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
