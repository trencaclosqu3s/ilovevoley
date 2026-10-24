"""Tareas de enriquecimiento y scraping mediante endpoints JSON."""

import json
import logging

from celery import chord, shared_task
from django.conf import settings
from django.core.mail import mail_admins
from django.db import models as django_models

from ilovevoley.competitions.models import League, Match, ScrapingEndpoint
from ilovevoley.teams.models import Club, Team
from ilovevoley.competitions.scraping.federation import FederationScraper
from ilovevoley.competitions.tasks_scraping import (
    _get_league,
    _mail_admins_on_errors,
    build_scrape_all_leagues_workflow,
)

logger = logging.getLogger(__name__)

def _enrich_league(league, json_url=None):
    """Enriquece una liga con el JSON de la federación y devuelve sus estadísticas."""
    stats = {'league': league.name, 'success': True, 'enriched': 0, 'new': 0, 'errors': []}
    try:
        scraper = FederationScraper(league)
        result = scraper.enrich_matches_with_json(json_url=json_url) if json_url else scraper.enrich_matches_with_json()
        if 'error' in result:
            logger.error(f'{league.name} - Error: {result["error"]}')
            stats['success'] = False
            stats['errors'].append({'league': league.name, 'error': result['error']})
        else:
            stats['enriched'] = result.get('enriched_matches', 0)
            stats['new'] = result.get('new_matches', 0)
            logger.info(f'{league.name}: {stats["enriched"]} partidos enriquecidos, {stats["new"]} partidos nuevos')
    except Exception as e:
        stats['success'] = False
        logger.error(f'Error crítico en {league.name}: {e}', exc_info=True)
        stats['errors'].append({'league': league.name, 'error': str(e)})
    return stats


def _summarize_enrichment(league_stats):
    return {
        'status': 'success',
        'leagues_processed': len(league_stats),
        'leagues_success': sum(1 for s in league_stats if s['success']),
        'leagues_errors': sum(1 for s in league_stats if not s['success']),
        'total_enriched': sum(s['enriched'] for s in league_stats),
        'total_new': sum(s['new'] for s in league_stats),
        'errors': [e for s in league_stats for e in s['errors']],
    }


def _enrich_leagues_workflow(league_pks, delay, json_url=None, notify=True):
    """
    Una tarea por liga y un callback de resumen. La separación entre ligas es un
    `countdown` escalonado, no un `sleep` que retenga al worker (#601).
    """
    header = [
        enrich_league_stats_task.s(pk, json_url).set(countdown=i * delay)
        for i, pk in enumerate(league_pks)
    ]
    return chord(header)(enrich_leagues_summary_task.s(notify=notify))


@shared_task(name='enrich_league_stats', bind=True)
def enrich_league_stats_task(self, league_pk, json_url=None):
    """Enriquece una liga y devuelve sus estadísticas (parte del chord de enrich_matches_json)."""
    league, failed = _get_league(league_pk, {'enriched': 0, 'new': 0})
    return failed or _enrich_league(league, json_url)


@shared_task(name='enrich_leagues_summary', bind=True)
def enrich_leagues_summary_task(self, league_stats, notify=True):
    """Callback del chord: agrega las estadísticas por liga y avisa a admins si hubo errores."""
    total_results = _summarize_enrichment(league_stats)
    logger.info(
        f"Enriquecimiento JSON completado - Procesadas: {total_results['leagues_processed']}, "
        f"Exitosas: {total_results['leagues_success']}, "
        f"Con errores: {total_results['leagues_errors']}, "
        f"Partidos enriquecidos: {total_results['total_enriched']}, "
        f"Partidos nuevos: {total_results['total_new']}"
    )
    if notify and total_results['leagues_errors'] > 0:
        subject = "[VideosVoley] Errores en enriquecimiento JSON de partidos"
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
        _mail_admins_on_errors(subject, message)
    return total_results


@shared_task(name='enrich_matches_json', bind=True)
def enrich_matches_json_task(self, league_id=None, delay=1.0):
    """
    Ejecuta enriquecimiento de partidos con datos JSON de la federación.

    Si se proporciona league_id, enriquece solo esa liga (en línea, sin espera).
    Si no, lanza una tarea por liga activa; el resumen y el email de errores
    los produce `enrich_leagues_summary`.

    Args:
        league_id: ID de la federación de la liga (opcional)
        delay: Segundos entre el arranque de una liga y la siguiente (default: 1.0)
    """
    logger.info("Iniciando enriquecimiento de partidos con datos JSON")

    if league_id:
        try:
            league = League.objects.get(federation_id=league_id, is_active=True)
        except League.DoesNotExist:
            error_msg = f'Liga con ID {league_id} no encontrada o inactiva'
            logger.error(error_msg)
            return {'status': 'error', 'message': error_msg}
        return _summarize_enrichment([_enrich_league(league)])

    league_pks = list(League.objects.filter(is_active=True).values_list('pk', flat=True))
    if not league_pks:
        error_msg = 'No se encontraron ligas activas'
        logger.warning(error_msg)
        return {'status': 'error', 'message': error_msg}
    _enrich_leagues_workflow(league_pks, delay)
    return {'status': 'queued', 'leagues_queued': len(league_pks)}


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
        
        from ilovevoley.competitions.scraping.federation import FederationScraper
        
        # Usar endpoint específico para próximos partidos
        json_url = "https://www.voleibolib.net/JSON/get_partidos_desglose_competiciones.asp?op=1&fini=&ffin="
        
        # Obtener todas las ligas activas
        from ilovevoley.competitions.models import League
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
        
        league_pks = [league.pk for league in leagues]
        if not league_pks:
            return {'status': 'error', 'error': 'No hay ligas activas para enriquecer'}
        _enrich_leagues_workflow(league_pks, delay, json_url=json_url, notify=False)
        return {'status': 'queued', 'leagues_queued': len(league_pks)}

    except Exception as e:
        error_msg = f"Error en enriquecimiento de próximos partidos: {str(e)}"
        logger.error(error_msg)
        return {'status': 'error', 'error': error_msg}

@shared_task(name='scrape_and_enrich_all', bind=True)
def scrape_and_enrich_all_task(self, round_number=None, category_filter=None, delay=2.0):
    """
    Lanza el scraping de todas las ligas y, al terminar el último, el enriquecimiento JSON.

    Args:
        round_number: Jornada específica (opcional)
        category_filter: Filtrar solo ligas de una categoría específica (opcional)
        delay: Segundos entre el arranque de cada liga y entre operaciones (default: 2.0)

    Returns:
        dict: Ligas encoladas; el resumen del scraping y el del enriquecimiento
        los registran sus propias tareas.
    """
    logger.info("Iniciando scraping completo + enriquecimiento JSON")
    workflow, queued = build_scrape_all_leagues_workflow(
        round_number, category_filter, delay, then=enrich_matches_json_task.si(delay=delay)
    )
    if not workflow:
        # Sin ligas no hay scraping, pero el enriquecimiento sigue su curso como antes.
        enrich_matches_json_task.delay(delay=delay)
        return {'status': 'partial_success', 'leagues_queued': 0}
    return {'status': 'queued', 'leagues_queued': queued}


@shared_task(name='scrape_json_results', bind=True)
def scrape_json_results_task(self, league_id=None, category_filter=None, delay=1.0, create_endpoint=False):
    """
    Ejecuta scraping de resultados usando el endpoint JSON op=0 (op=2 dejó de ser válido, #463).
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
    json_url = "https://www.voleibolib.net/JSON/get_partidos_desglose_competiciones.asp?op=0&fini=&ffin="
    
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
    """Procesa los partidos encontrados en un grupo específico del JSON de resultados."""
    scraper = FederationScraper(league)
    return scraper._process_json_matches_unified(league, partidos_data, categoria_name, grupo_id, op_type='2')



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
            from ilovevoley.competitions.models import ScrapingEndpoint
            
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
    'cache_federation_logos_task',
]


@shared_task(name='cache_federation_logos')
def cache_federation_logos_task():
    """Guarda en local el escudo de los clubes y equipos que aún no tienen copia.

    Idempotente: solo toca los que tienen ``logo`` vacío, así que los fallos de
    red se reintentan en la siguiente ejecución. Para refrescar un escudo basta
    con vaciar su campo ``logo``.
    """
    from ilovevoley.teams.services import cache_logo

    saved = failed = 0
    clubs = Club.objects.filter(logo='').exclude(federation_id='')
    teams = Team.objects.filter(logo='').exclude(logo_url__isnull=True).exclude(logo_url='')
    for obj in [*clubs, *teams]:
        if cache_logo(obj):
            saved += 1
        else:
            failed += 1
    return {'saved': saved, 'failed': failed}
