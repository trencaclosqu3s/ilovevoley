"""Tareas de enriquecimiento y scraping mediante endpoints JSON."""

import logging
import time

from celery import shared_task
from django.conf import settings
from django.core.mail import mail_admins
from django.db import models as django_models

from ..models import Club, League, Match, ScrapingEndpoint, Team
from ..scraping import FederationScraper
from .scraping import scrape_all_leagues_task

logger = logging.getLogger(__name__)

@shared_task(name='enrich_matches_json', bind=True)
def enrich_matches_json_task(self, league_id=None, delay=1.0):
    """
    Ejecuta enriquecimiento de partidos con datos JSON de la federación.
    
    Si se proporciona league_id, enriquece solo esa liga.
    Si no se proporciona, enriquece todas las ligas activas.
    
    Args:
        league_id: ID de la federación de la liga (opcional)
        delay: Tiempo de espera entre ligas en segundos (default: 1.0)
    
    Returns:
        dict: Estadísticas del enriquecimiento realizado
    """
    logger.info("Iniciando enriquecimiento de partidos con datos JSON")
    
    try:
        if league_id:
            # Enriquecimiento de una liga específica
            try:
                league = League.objects.get(federation_id=league_id, is_active=True)
            except League.DoesNotExist:
                error_msg = f'Liga con ID {league_id} no encontrada o inactiva'
                logger.error(error_msg)
                return {'status': 'error', 'message': error_msg}
            
            leagues = [league]
        else:
            # Enriquecimiento de todas las ligas activas
            leagues = League.objects.filter(is_active=True).prefetch_related('categories')
            
            if not leagues.exists():
                error_msg = 'No se encontraron ligas activas'
                logger.warning(error_msg)
                return {'status': 'error', 'message': error_msg}
        
        total_results = {
            'status': 'success',
            'leagues_processed': 0,
            'leagues_success': 0,
            'leagues_errors': 0,
            'total_enriched': 0,
            'total_new': 0,
            'errors': []
        }
        
        for i, league in enumerate(leagues):
            # Obtener nombres de todas las categorías
            categories = league.categories.all()
            category_name = ', '.join([c.name for c in categories]) if categories else 'Sin categoría'
            logger.info(f'[{i+1}/{len(leagues)}] Enriqueciendo partidos de {league.name} ({category_name})')
            
            try:
                scraper = FederationScraper(league)
                result = scraper.enrich_matches_with_json()
                
                if 'error' in result:
                    logger.error(f'{league.name} - Error: {result["error"]}')
                    total_results['leagues_errors'] += 1
                    total_results['errors'].append({
                        'league': league.name,
                        'error': result['error']
                    })
                else:
                    enriched = result.get('enriched_matches', 0)
                    new_matches = result.get('new_matches', 0)
                    
                    total_results['total_enriched'] += enriched
                    total_results['total_new'] += new_matches
                    total_results['leagues_success'] += 1
                    
                    logger.info(f'{league.name}: {enriched} partidos enriquecidos, {new_matches} partidos nuevos')
                
                total_results['leagues_processed'] += 1
                
                # Rate limiting entre ligas
                if i < len(leagues) - 1:
                    time.sleep(delay)
            
            except Exception as e:
                total_results['leagues_errors'] += 1
                total_results['leagues_processed'] += 1
                error_msg = f'Error crítico en {league.name}: {str(e)}'
                logger.error(error_msg, exc_info=True)
                total_results['errors'].append({
                    'league': league.name,
                    'error': str(e)
                })
        
        # Log resumen final
        logger.info(
            f"Enriquecimiento JSON completado - Procesadas: {total_results['leagues_processed']}, "
            f"Exitosas: {total_results['leagues_success']}, "
            f"Con errores: {total_results['leagues_errors']}, "
            f"Partidos enriquecidos: {total_results['total_enriched']}, "
            f"Partidos nuevos: {total_results['total_new']}"
        )
        
        # Enviar email a admins si hay errores y las notificaciones están habilitadas
        if total_results['leagues_errors'] > 0 and settings.NOTIFICATION_EMAIL_ENABLED:
            subject = f"[VideosVoley] Errores en enriquecimiento JSON de partidos"
            message = f"""
            Se han detectado errores durante el enriquecimiento JSON de partidos:
            
            - Ligas procesadas: {total_results['leagues_processed']}
            - Ligas exitosas: {total_results['leagues_success']}
            - Ligas con errores: {total_results['leagues_errors']}
            
            Datos obtenidos:
            - Partidos enriquecidos: {total_results['total_enriched']}
            - Partidos nuevos: {total_results['total_new']}
            
            Errores detectados:
            {chr(10).join([f"- {e['league']}: {e['error']}" for e in total_results['errors'][:10]])}
            """
            
            try:
                mail_admins(subject, message, fail_silently=True)
            except Exception as e:
                logger.error(f"Error enviando email de notificación: {e}")
        
        return total_results
    
    except Exception as e:
        error_msg = f'Error general durante enriquecimiento JSON: {str(e)}'
        logger.error(error_msg, exc_info=True)
        return {
            'status': 'error',
            'message': error_msg
        }


@shared_task(name='enrich_single_league_json', bind=True)
def enrich_single_league_json_task(self, league_id, delay=1.0):
    """
    Ejecuta enriquecimiento JSON de una liga específica.
    
    Args:
        league_id: ID de la federación de la liga a enriquecer
        delay: Tiempo de espera en segundos (default: 1.0)
    
    Returns:
        dict: Resultados del enriquecimiento
    """
    logger.info(f"Iniciando enriquecimiento JSON de liga con ID: {league_id}")
    
    try:
        league = League.objects.get(federation_id=league_id, is_active=True)
    except League.DoesNotExist:
        error_msg = f'Liga con ID {league_id} no encontrada o inactiva'
        logger.error(error_msg)
        return {'status': 'error', 'message': error_msg}
    
    logger.info(f'Enriqueciendo liga: {league.name}')
    
    scraper = FederationScraper(league)
    
    try:
        result = scraper.enrich_matches_with_json()
        
        if 'error' in result:
            logger.error(f'Error: {result["error"]}')
            return {
                'status': 'error',
                'league': league.name,
                'league_id': league_id,
                'message': result['error']
            }
        
        enriched = result.get('enriched_matches', 0)
        new_matches = result.get('new_matches', 0)
        
        summary = {
            'status': 'success',
            'league': league.name,
            'league_id': league_id,
            'enriched_matches': enriched,
            'new_matches': new_matches,
            'total_processed': enriched + new_matches
        }
        
        logger.info(f'Enriquecimiento completado para {league.name}: {enriched} enriquecidos, {new_matches} nuevos')
        return summary
    
    except Exception as e:
        error_msg = f'Error durante enriquecimiento: {str(e)}'
        logger.error(error_msg, exc_info=True)
        return {
            'status': 'error',
            'league': league.name,
            'league_id': league_id,
            'message': error_msg
        }


@shared_task(name='enrich_upcoming_matches', bind=True)
def enrich_upcoming_matches_task(self, delay=1.0):
    """
    Enriquece partidos próximos usando el endpoint op=1 que muestra los próximos partidos
    """
    try:
        logger.info("Iniciando enriquecimiento de partidos próximos con datos JSON")
        
        from ilovevoley.videos.scraping import FederationScraper
        
        # Usar endpoint específico para próximos partidos
        json_url = "https://www.voleibolib.net/JSON/get_partidos_desglose_competiciones.asp?op=1&fini=&ffin="
        
        # Obtener todas las ligas activas
        from ilovevoley.videos.models import League
        leagues = League.objects.filter(is_active=True)
        
        # Filtrar solo ligas que tienen datos en el JSON actual
        leagues_with_data = []
        try:
            import requests
            response = requests.get(json_url, timeout=30)
            json_data = json.loads(response.text)
            
            # Obtener IDs de grupos disponibles en el JSON
            available_group_ids = set()
            for categoria in json_data.get('categorias', []):
                for competicion in categoria.get('competiciones', []):
                    for fase in competicion.get('fases', []):
                        for grupo in fase.get('grupos', []):
                            available_group_ids.add(grupo.get('id'))
            
            # Filtrar ligas que tienen datos en el JSON
            for league in leagues:
                if str(league.federation_id) in available_group_ids:
                    leagues_with_data.append(league)
                else:
                    logger.info(f"Saltando {league.name} - No hay datos en el JSON (federation_id: {league.federation_id})")
            
            leagues = leagues_with_data
            logger.info(f"Ligas con datos en JSON: {len(leagues)} de {League.objects.filter(is_active=True).count()}")
            
        except Exception as e:
            logger.warning(f"No se pudo filtrar ligas por datos JSON: {e}. Procesando todas las ligas activas.")
        
        total_enriched = 0
        total_new = 0
        leagues_processed = 0
        leagues_success = 0
        leagues_errors = 0
        errors = []
        
        for league in leagues:
            try:
                leagues_processed += 1
                # Obtener nombres de todas las categorías
                categories = league.categories.all()
                category_name = ', '.join([c.name for c in categories]) if categories else 'Sin categoría'
                logger.info(f"[{leagues_processed}/{leagues.count()}] Enriqueciendo partidos próximos de {league.name} ({category_name})")
                
                # Crear scraper y enriquecer con endpoint de próximos partidos
                scraper = FederationScraper(league)
                result = scraper.enrich_matches_with_json(json_url=json_url)
                
                if result.get('status') == 'success':
                    enriched = result.get('enriched_matches', 0)
                    new = result.get('new_matches', 0)
                    total_enriched += enriched
                    total_new += new
                    leagues_success += 1
                    logger.info(f"{league.name}: {enriched} partidos enriquecidos, {new} partidos nuevos")
                else:
                    leagues_errors += 1
                    error_msg = f"{league.name}: {result.get('error', 'Error desconocido')}"
                    errors.append(error_msg)
                    logger.error(error_msg)
                
                # Delay entre ligas
                if delay > 0:
                    time.sleep(delay)
                    
            except Exception as e:
                leagues_errors += 1
                error_msg = f"Error procesando {league.name}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        result = {
            'status': 'success',
            'leagues_processed': leagues_processed,
            'leagues_success': leagues_success,
            'leagues_errors': leagues_errors,
            'total_enriched': total_enriched,
            'total_new': total_new,
            'errors': errors
        }
        
        logger.info(f"Enriquecimiento de próximos partidos completado - Procesadas: {leagues_processed}, Exitosas: {leagues_success}, Con errores: {leagues_errors}, Partidos enriquecidos: {total_enriched}, Partidos nuevos: {total_new}")
        return result
        
    except Exception as e:
        error_msg = f"Error en enriquecimiento de próximos partidos: {str(e)}"
        logger.error(error_msg)
        return {'status': 'error', 'error': error_msg}

@shared_task(name='scrape_and_enrich_all', bind=True)
def scrape_and_enrich_all_task(self, round_number=None, category_filter=None, delay=2.0):
    """
    Ejecuta scraping completo seguido de enriquecimiento JSON.
    
    Args:
        round_number: Jornada específica (opcional)
        category_filter: Filtrar solo ligas de una categoría específica (opcional)
        delay: Tiempo de espera entre operaciones en segundos (default: 2.0)
    
    Returns:
        dict: Estadísticas combinadas del scraping y enriquecimiento
    """
    logger.info("Iniciando scraping completo + enriquecimiento JSON")
    
    # 1. Ejecutar scraping normal
    logger.info("=== FASE 1: Scraping normal ===")
    scrape_results = scrape_all_leagues_task(
        round_number=round_number,
        category_filter=category_filter,
        delay=delay
    )

    # 2. Ejecutar enriquecimiento JSON
    logger.info("=== FASE 2: Enriquecimiento JSON ===")
    enrich_results = enrich_matches_json_task(delay=delay)
    
    # 3. Combinar resultados
    combined_results = {
        'status': 'success',
        'scraping': scrape_results,
        'enrichment': enrich_results,
        'summary': {
            'leagues_processed': scrape_results.get('leagues_processed', 0),
            'leagues_success': scrape_results.get('leagues_success', 0),
            'leagues_errors': scrape_results.get('leagues_errors', 0),
            'total_teams': scrape_results.get('total_teams', 0),
            'total_matches': scrape_results.get('total_matches', 0),
            'total_standings': scrape_results.get('total_standings', 0),
            'enriched_matches': enrich_results.get('total_enriched', 0),
            'new_matches_from_json': enrich_results.get('total_new', 0)
        }
    }
    
    # Determinar estado general
    if scrape_results.get('status') == 'error' and enrich_results.get('status') == 'error':
        combined_results['status'] = 'error'
    elif scrape_results.get('status') == 'error' or enrich_results.get('status') == 'error':
        combined_results['status'] = 'partial_success'
    
    logger.info(
        f"Scraping + Enriquecimiento completado - "
        f"Ligas: {combined_results['summary']['leagues_processed']}, "
        f"Equipos: {combined_results['summary']['total_teams']}, "
        f"Partidos: {combined_results['summary']['total_matches']}, "
        f"Enriquecidos: {combined_results['summary']['enriched_matches']}, "
        f"Nuevos desde JSON: {combined_results['summary']['new_matches_from_json']}"
    )
    
    return combined_results


@shared_task(name='scrape_json_results', bind=True)
def scrape_json_results_task(self, league_id=None, category_filter=None, delay=1.0, create_endpoint=False):
    """
    Ejecuta scraping de resultados usando el endpoint JSON op=2.
    Usa el nuevo sistema unificado para máxima eficiencia.
    
    Args:
        league_id: ID de la liga específica a procesar (opcional)
        category_filter: Filtrar solo ligas de una categoría específica (opcional)
        delay: Tiempo de espera entre requests en segundos (default: 1.0)
        create_endpoint: Crear endpoint de resultados JSON si no existe (default: False)
    
    Returns:
        dict: Estadísticas del scraping realizado
    """
    # Usar la tarea genérica para procesar resultados
    json_url = "https://www.voleibolib.net/JSON/get_partidos_desglose_competiciones.asp?op=2&fini=&ffin="
    
    return process_json_unified_task(
        json_url=json_url,
        op_type='2',
        league_id=league_id,
        category_filter=category_filter,
        delay=delay,
        create_endpoint=create_endpoint
    )


@shared_task(name='scrape_json_upcoming', bind=True)
def scrape_json_upcoming_task(self, league_id=None, category_filter=None, delay=1.0, create_endpoint=False):
    """
    Ejecuta scraping de partidos próximos usando el endpoint JSON op=1.
    Usa el nuevo sistema unificado para máxima eficiencia.
    
    Args:
        league_id: ID de la liga específica a procesar (opcional)
        category_filter: Filtrar solo ligas de una categoría específica (opcional)
        delay: Tiempo de espera entre requests en segundos (default: 1.0)
        create_endpoint: Crear endpoint de partidos próximos JSON si no existe (default: False)
    
    Returns:
        dict: Estadísticas del scraping realizado
    """
    # Usar la tarea genérica para procesar partidos próximos
    json_url = "https://www.voleibolib.net/JSON/get_partidos_desglose_competiciones.asp?op=1&fini=&ffin="
    
    return process_json_unified_task(
        json_url=json_url,
        op_type='1',
        league_id=league_id,
        category_filter=category_filter,
        delay=delay,
        create_endpoint=create_endpoint
    )


def _process_json_matches_from_group(league, partidos_data, categoria_name, grupo_id):
    """Procesa los partidos encontrados en un grupo específico del JSON de resultados"""
    from unidecode import unidecode
    from datetime import datetime
    from django.utils import timezone
    
    matches_created = 0
    matches_updated = 0
    
    for partido_data in partidos_data:
        try:
            # Extraer equipos
            home_team_name = (partido_data.get('ELOCAL') or '').strip()
            away_team_name = (partido_data.get('EVISITANTE') or '').strip()
            
            if not home_team_name or not away_team_name:
                continue
            
            # Parsear fecha y hora
            fecha_str = partido_data.get('FECHA', '')
            hora_str = partido_data.get('HORA', '')
            
            if not fecha_str:
                continue
            
            try:
                if hora_str:
                    match_datetime = datetime.strptime(f"{fecha_str} {hora_str}", "%d/%m/%Y %H:%M")
                else:
                    match_datetime = datetime.strptime(fecha_str, "%d/%m/%Y")
                
                match_datetime = timezone.make_aware(match_datetime)
            except ValueError:
                continue
            
            # Extraer resultados - verificar que el partido tenga resultados válidos
            home_score = partido_data.get('RESULTADO_LOCAL')
            away_score = partido_data.get('RESULTADO_VISITANTE')
            
            if home_score is None or away_score is None:
                continue
            
            # Buscar equipos
            home_team = _find_team_by_name(home_team_name, league)
            away_team = _find_team_by_name(away_team_name, league)
            
            if not home_team or not away_team:
                logger.debug(f'Saltando partido: {home_team_name} vs {away_team_name} (equipos no encontrados)')
                continue
            
            # Buscar partido existente
            match = Match.objects.filter(
                home_team=home_team,
                away_team=away_team,
                match_date=match_datetime
            ).first()
            
            if match:
                # Actualizar partido existente
                match.home_score = home_score
                match.away_score = away_score
                match.status = 'finished'
                match.venue = (partido_data.get('Campo') or '').strip()
                match.city = (partido_data.get('Municipio') or '').strip()
                match.referee1 = (partido_data.get('arbitro1') or '').strip()
                match.referee2 = (partido_data.get('arbitro2') or '').strip()
                match.scorer = (partido_data.get('anotador') or '').strip()
                match.timekeeper = (partido_data.get('cronometrador') or '').strip()
                match.delegate = (partido_data.get('delegado') or '').strip()
                match.field_address = (partido_data.get('Direccion_Campo') or '').strip()
                match.federation_id = str(partido_data.get('ID', ''))
                match.acta_html = (partido_data.get('acta_html') or '').strip()
                match.save()
                matches_updated += 1
                
                logger.debug(f'Actualizado: {home_team.name} {match.home_score}-{match.away_score} {away_team.name}')
            else:
                # Crear nuevo partido
                match = Match.objects.create(
                    league=league,
                    home_team=home_team,
                    away_team=away_team,
                    match_date=match_datetime,
                    home_score=home_score,
                    away_score=away_score,
                    status='finished',
                    venue=(partido_data.get('Campo') or '').strip(),
                    city=(partido_data.get('Municipio') or '').strip(),
                    referee1=(partido_data.get('arbitro1') or '').strip(),
                    referee2=(partido_data.get('arbitro2') or '').strip(),
                    scorer=(partido_data.get('anotador') or '').strip(),
                    timekeeper=(partido_data.get('cronometrador') or '').strip(),
                    delegate=(partido_data.get('delegado') or '').strip(),
                    field_address=(partido_data.get('Direccion_Campo') or '').strip(),
                    federation_id=str(partido_data.get('ID', '')),
                    acta_html=(partido_data.get('acta_html') or '').strip(),
                    round_number=1  # El JSON no incluye jornada
                )
                matches_created += 1
                
                logger.debug(f'Creado: {home_team.name} {match.home_score}-{match.away_score} {away_team.name}')
                
        except Exception as e:
            logger.error(f'Error procesando partido {partido_data.get("ELOCAL", "Unknown")} vs {partido_data.get("EVISITANTE", "Unknown")}: {str(e)}')
            continue
    
    return matches_created, matches_updated




def _find_team_by_name(team_name: str, league) -> 'Team':
    """Busca un equipo por nombre en la liga"""
    from unidecode import unidecode
    
    if not team_name:
        return None


@shared_task(name='process_json_unified', bind=True)
def process_json_unified_task(self, json_url, op_type='1', league_id=None, category_filter=None, delay=1.0, create_endpoint=False):
    """
    Tarea genérica para procesar cualquier endpoint JSON de forma unificada.
    
    Args:
        json_url: URL del endpoint JSON
        op_type: Tipo de operación ('1' para próximos, '2' para resultados, etc.)
        league_id: ID de la liga específica a procesar (opcional)
        category_filter: Filtrar solo ligas de una categoría específica (opcional)
        delay: Tiempo de espera entre requests en segundos (default: 1.0)
        create_endpoint: Crear endpoint si no existe (default: False)
    
    Returns:
        dict: Estadísticas del procesamiento realizado
    """
    logger.info(f"Iniciando procesamiento JSON unificado (op={op_type}) desde: {json_url}")
    
    try:
        # Obtener ligas activas para validación
        leagues = League.objects.filter(is_active=True).prefetch_related('categories')
        
        # Filtrar por liga específica si se especifica
        if league_id:
            leagues = leagues.filter(id=league_id)
        
        # Filtrar por categoría si se especifica
        if category_filter:
            leagues = leagues.filter(categories__name__icontains=category_filter).distinct()
        
        if not leagues.exists():
            error_msg = f'No se encontraron ligas activas'
            if league_id:
                error_msg += f' con ID {league_id}'
            if category_filter:
                error_msg += f" de categoría '{category_filter}'"
            logger.warning(error_msg)
            return {'status': 'error', 'message': error_msg}
        
        # Usar el sistema unificado para procesar el JSON
        reference_league = leagues.first()
        scraper = FederationScraper(reference_league)
        
        result = scraper.process_json_unified(
            json_url=json_url,
            op_type=op_type,
            filter_by_db_leagues=True
        )
        
        # Crear endpoints si es necesario
        if create_endpoint and result.get('status') == 'success':
            from ilovevoley.videos.models import ScrapingEndpoint
            
            # Determinar el tipo de endpoint según op_type
            if op_type == '1':
                endpoint_type = 'json_matches'
                parser_type = 'json_matches'
            elif op_type == '2':
                endpoint_type = 'json_results'
                parser_type = 'json_results'
            else:
                endpoint_type = 'json_unified'
                parser_type = 'json_unified'
            
            for league in leagues:
                endpoint = league.endpoints.filter(
                    endpoint_type=endpoint_type,
                    is_active=True
                ).first()
                
                if not endpoint:
                    ScrapingEndpoint.objects.create(
                        league=league,
                        endpoint_type=endpoint_type,
                        url_pattern=json_url,
                        parser_type=parser_type,
                        is_active=True,
                        extra_params={'op_type': op_type}
                    )
                    logger.info(f'Endpoint {endpoint_type} creado para {league.name}')
        
        # Enviar email de notificación si hay errores y está habilitado
        if result.get('errors') and getattr(settings, 'NOTIFICATION_EMAIL_ENABLED', False):
            try:
                subject = f'Errores en procesamiento JSON (op={op_type}) - {result.get("leagues_errors", 0)} ligas con problemas'
                message = f'Se encontraron errores en {result.get("leagues_errors", 0)} de {result.get("leagues_processed", 0)} ligas procesadas.\n\n'
                message += 'Errores detallados:\n'
                for error in result.get('errors', []):
                    message += f'- {error["league"]}: {error["error"]}\n'
                
                mail_admins(subject, message)
                logger.info('Email de notificación de errores enviado')
            except Exception as e:
                logger.error(f'Error enviando email de notificación: {e}')
        
        return result
        
    except Exception as e:
        error_msg = f'Error general en procesamiento JSON unificado: {str(e)}'
        logger.error(error_msg, exc_info=True)
        return {'status': 'error', 'message': error_msg}
    
    # Normalizar nombre para búsqueda
    normalized_name = unidecode(team_name.upper())
    normalized_name = ''.join(c for c in normalized_name if c.isalnum() or c.isspace())
    normalized_name = ' '.join(normalized_name.split())
    
    # Obtener las categorías de la liga
    league_categories = league.categories.all()

    # Buscar por nombre exacto primero
    team = Team.objects.filter(
        name__iexact=team_name,
        category__in=league_categories
    ).first()

    if team:
        return team

    # Buscar por nombre normalizado
    for team in Team.objects.filter(category__in=league_categories):
        team_normalized = unidecode(team.name.upper())
        team_normalized = ''.join(c for c in team_normalized if c.isalnum() or c.isspace())
        team_normalized = ' '.join(team_normalized.split())
        
        if team_normalized == normalized_name:
            return team

    return None

__all__ = [
    'enrich_matches_json_task',
    'enrich_single_league_json_task',
    'enrich_upcoming_matches_task',
    'scrape_and_enrich_all_task',
    'scrape_json_results_task',
    'scrape_json_upcoming_task',
    'process_json_unified_task',
]
