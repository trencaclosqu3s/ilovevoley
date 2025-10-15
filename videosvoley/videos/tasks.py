"""
Tareas de Celery para scraping automático de datos de voleibol.

Estas tareas pueden ejecutarse manualmente desde código o configurarse
como tareas periódicas desde el admin de Django (django-celery-beat).
"""

import logging
import time
from celery import shared_task
from django.core.mail import mail_admins
from django.conf import settings

from django.db import models as django_models
from videosvoley.videos.models import League, Club, Team, Match
from videosvoley.videos.scraping import FederationScraper

logger = logging.getLogger(__name__)


@shared_task(name='scrape_all_leagues', bind=True)
def scrape_all_leagues_task(self, round_number=None, category_filter=None, delay=2.0):
    """
    Ejecuta scraping de todas las ligas activas.
    
    Args:
        round_number: Jornada específica (opcional)
        category_filter: Filtrar solo ligas de una categoría específica (opcional)
        delay: Tiempo de espera entre ligas en segundos (default: 2.0)
    
    Returns:
        dict: Estadísticas del scraping realizado
    """
    logger.info(f"Iniciando tarea de scraping de todas las ligas activas")
    
    # Obtener ligas activas
    leagues = League.objects.filter(is_active=True).select_related('category')
    
    # Filtrar por categoría si se especifica
    if category_filter:
        leagues = leagues.filter(category__name__icontains=category_filter)
    
    if not leagues.exists():
        error_msg = f'No se encontraron ligas activas'
        if category_filter:
            error_msg += f" de categoría '{category_filter}'"
        logger.warning(error_msg)
        return {'status': 'error', 'message': error_msg}
    
    total_results = {
        'status': 'success',
        'leagues_processed': 0,
        'leagues_success': 0,
        'leagues_errors': 0,
        'total_teams': 0,
        'total_matches': 0,
        'total_standings': 0,
        'errors': []
    }
    
    for i, league in enumerate(leagues):
        category_name = league.category.name if league.category else 'Sin categoría'
        logger.info(f'[{i+1}/{leagues.count()}] Procesando {league.name} ({category_name})')
        
        try:
            scraper = FederationScraper(league)
            results = scraper.scrape_all_endpoints(round=round_number)
            
            # Procesar resultados
            league_success = True
            league_stats = {'teams': 0, 'matches': 0, 'standings': 0}
            
            for endpoint_type, data in results.items():
                if 'error' in data:
                    logger.error(f'{league.name} - {endpoint_type}: {data["error"]}')
                    league_success = False
                    total_results['errors'].append({
                        'league': league.name,
                        'endpoint': endpoint_type,
                        'error': data['error']
                    })
                else:
                    teams_count = len(data.get('teams', []))
                    standings_count = len(data.get('standings', []))
                    matches_count = len(data.get('matches', []))
                    
                    league_stats['teams'] += teams_count
                    league_stats['matches'] += matches_count
                    league_stats['standings'] += standings_count
            
            # Actualizar estadísticas totales
            total_results['leagues_processed'] += 1
            if league_success:
                total_results['leagues_success'] += 1
                logger.info(
                    f'{league.name}: {league_stats["teams"]} equipos, '
                    f'{league_stats["matches"]} partidos, '
                    f'{league_stats["standings"]} clasificaciones'
                )
            else:
                total_results['leagues_errors'] += 1
            
            total_results['total_teams'] += league_stats['teams']
            total_results['total_matches'] += league_stats['matches']
            total_results['total_standings'] += league_stats['standings']
            
            # Rate limiting entre ligas
            if i < leagues.count() - 1:
                time.sleep(delay)
        
        except Exception as e:
            total_results['leagues_errors'] += 1
            total_results['leagues_processed'] += 1
            error_msg = f'Error crítico en {league.name}: {str(e)}'
            logger.error(error_msg, exc_info=True)
            total_results['errors'].append({
                'league': league.name,
                'endpoint': 'general',
                'error': str(e)
            })
    
    # Log resumen final
    logger.info(
        f"Scraping completado - Procesadas: {total_results['leagues_processed']}, "
        f"Exitosas: {total_results['leagues_success']}, "
        f"Con errores: {total_results['leagues_errors']}"
    )
    
    # Enviar email a admins si hay errores y las notificaciones están habilitadas
    if total_results['leagues_errors'] > 0 and settings.NOTIFICATION_EMAIL_ENABLED:
        subject = f"[I Love Voley] Errores en scraping automático de ligas"
        message = f"""
        Se han detectado errores durante el scraping automático de ligas:
        
        - Ligas procesadas: {total_results['leagues_processed']}
        - Ligas exitosas: {total_results['leagues_success']}
        - Ligas con errores: {total_results['leagues_errors']}
        
        Datos obtenidos:
        - Equipos: {total_results['total_teams']}
        - Partidos: {total_results['total_matches']}
        - Clasificaciones: {total_results['total_standings']}
        
        Errores detectados:
        {chr(10).join([f"- {e['league']} ({e['endpoint']}): {e['error']}" for e in total_results['errors'][:10]])}
        """
        
        try:
            mail_admins(subject, message, fail_silently=True)
        except Exception as e:
            logger.error(f"Error enviando email de notificación: {e}")
    
    return total_results


@shared_task(name='scrape_league', bind=True)
def scrape_league_task(self, league_id, round_number=None):
    """
    Ejecuta scraping de una liga específica.
    
    Args:
        league_id: ID de la federación de la liga a scrapear
        round_number: Jornada específica (opcional)
    
    Returns:
        dict: Resultados del scraping
    """
    logger.info(f"Iniciando scraping de liga con ID: {league_id}")
    
    try:
        league = League.objects.get(federation_id=league_id, is_active=True)
    except League.DoesNotExist:
        error_msg = f'Liga con ID {league_id} no encontrada o inactiva'
        logger.error(error_msg)
        return {'status': 'error', 'message': error_msg}
    
    logger.info(f'Scrapeando liga: {league.name}')
    
    scraper = FederationScraper(league)
    
    try:
        results = scraper.scrape_all_endpoints(round=round_number)
        
        # Procesar resultados
        summary = {
            'status': 'success',
            'league': league.name,
            'league_id': league_id,
            'endpoints': {},
            'errors': []
        }
        
        for endpoint_type, data in results.items():
            if 'error' in data:
                logger.error(f'{endpoint_type}: {data["error"]}')
                summary['endpoints'][endpoint_type] = {'status': 'error', 'error': data['error']}
                summary['errors'].append({'endpoint': endpoint_type, 'error': data['error']})
            else:
                teams_count = len(data.get('teams', []))
                standings_count = len(data.get('standings', []))
                matches_count = len(data.get('matches', []))
                
                summary['endpoints'][endpoint_type] = {
                    'status': 'success',
                    'teams': teams_count,
                    'standings': standings_count,
                    'matches': matches_count
                }
                
                logger.info(
                    f'{endpoint_type}: {teams_count} equipos, '
                    f'{standings_count} clasificaciones, '
                    f'{matches_count} partidos'
                )
        
        if summary['errors']:
            summary['status'] = 'partial_success'
        
        logger.info(f'Scraping completado para {league.name}')
        return summary
    
    except Exception as e:
        error_msg = f'Error durante scraping: {str(e)}'
        logger.error(error_msg, exc_info=True)
        return {
            'status': 'error',
            'league': league.name,
            'league_id': league_id,
            'message': error_msg
        }


@shared_task(name='scrape_calendar', bind=True)
def scrape_calendar_task(self, league_id=None, delay=2.0):
    """
    Ejecuta scraping del calendario de partidos.
    
    Si se proporciona league_id, scrapea solo esa liga.
    Si no se proporciona, scrapea el calendario de todas las ligas activas.
    
    Args:
        league_id: ID de la federación de la liga (opcional)
        delay: Tiempo de espera entre ligas en segundos (default: 2.0)
    
    Returns:
        dict: Estadísticas del scraping realizado
    """
    logger.info("Iniciando scraping de calendario de partidos")
    
    try:
        if league_id:
            # Scraping de una liga específica
            try:
                league = League.objects.get(federation_id=league_id, is_active=True)
            except League.DoesNotExist:
                error_msg = f'Liga con ID {league_id} no encontrada o inactiva'
                logger.error(error_msg)
                return {'status': 'error', 'message': error_msg}
            
            leagues = [league]
        else:
            # Scraping de todas las ligas activas
            leagues = League.objects.filter(is_active=True).select_related('category')
            
            if not leagues.exists():
                error_msg = 'No se encontraron ligas activas'
                logger.warning(error_msg)
                return {'status': 'error', 'message': error_msg}
        
        total_results = {
            'status': 'success',
            'leagues_processed': 0,
            'leagues_success': 0,
            'leagues_errors': 0,
            'total_matches': 0,
            'errors': []
        }
        
        for i, league in enumerate(leagues):
            category_name = league.category.name if league.category else 'Sin categoría'
            logger.info(f'[{i+1}/{len(leagues)}] Procesando calendario de {league.name} ({category_name})')
            
            try:
                scraper = FederationScraper(league)
                
                # Buscar endpoint de calendario
                calendar_endpoint = league.endpoints.filter(
                    endpoint_type='calendar',
                    is_active=True
                ).first()
                
                if not calendar_endpoint:
                    logger.warning(f'No se encontró endpoint de calendario activo para {league.name}')
                    total_results['leagues_processed'] += 1
                    total_results['leagues_errors'] += 1
                    total_results['errors'].append({
                        'league': league.name,
                        'error': 'No se encontró endpoint de calendario activo'
                    })
                    continue
                
                # Ejecutar scraping del calendario
                result = scraper.scrape_endpoint(calendar_endpoint)
                
                if 'error' in result:
                    logger.error(f'{league.name} - Error: {result["error"]}')
                    total_results['leagues_errors'] += 1
                    total_results['errors'].append({
                        'league': league.name,
                        'error': result['error']
                    })
                else:
                    # Actualizar equipos si los hay
                    all_teams = {}
                    if 'teams' in result:
                        all_teams = scraper.update_teams(result['teams'])
                    
                    # Actualizar partidos en la base de datos
                    if 'matches' in result:
                        scraper.update_matches(result['matches'], all_teams)
                    
                    matches_count = len(result.get('matches', []))
                    total_results['total_matches'] += matches_count
                    total_results['leagues_success'] += 1
                    logger.info(f'{league.name}: {matches_count} partidos guardados en el calendario')
                
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
            f"Scraping de calendario completado - Procesadas: {total_results['leagues_processed']}, "
            f"Exitosas: {total_results['leagues_success']}, "
            f"Con errores: {total_results['leagues_errors']}"
        )
        
        # Enviar email a admins si hay errores y las notificaciones están habilitadas
        if total_results['leagues_errors'] > 0 and settings.NOTIFICATION_EMAIL_ENABLED:
            subject = f"[I Love Voley] Errores en scraping automático de calendario"
            message = f"""
            Se han detectado errores durante el scraping automático del calendario:
            
            - Ligas procesadas: {total_results['leagues_processed']}
            - Ligas exitosas: {total_results['leagues_success']}
            - Ligas con errores: {total_results['leagues_errors']}
            
            Partidos encontrados: {total_results['total_matches']}
            
            Errores detectados:
            {chr(10).join([f"- {e['league']}: {e['error']}" for e in total_results['errors'][:10]])}
            """
            
            try:
                mail_admins(subject, message, fail_silently=True)
            except Exception as e:
                logger.error(f"Error enviando email de notificación: {e}")
        
        return total_results
    
    except Exception as e:
        error_msg = f'Error general durante scraping de calendario: {str(e)}'
        logger.error(error_msg, exc_info=True)
        return {
            'status': 'error',
            'message': error_msg
        }


@shared_task(name='scrape_results', bind=True)
def scrape_results_task(self, league_id=None, round_number=None, delay=2.0):
    """
    Ejecuta scraping de resultados de partidos.
    
    Si se proporciona league_id, scrapea solo esa liga.
    Si no se proporciona, scrapea los resultados de todas las ligas activas.
    Si se proporciona round_number, scrapea solo esa jornada (legacy).
    Si no se proporciona round_number, scrapea TODAS las jornadas automáticamente.
    
    Args:
        league_id: ID de la federación de la liga (opcional)
        round_number: Jornada específica a scrapear (opcional, si no se provee scrapea todas)
        delay: Tiempo de espera entre jornadas/ligas en segundos (default: 2.0)
    
    Returns:
        dict: Estadísticas del scraping realizado
    """
    logger.info("Iniciando scraping de resultados de partidos")
    
    try:
        if league_id:
            # Scraping de una liga específica
            try:
                league = League.objects.get(federation_id=league_id, is_active=True)
            except League.DoesNotExist:
                error_msg = f'Liga con ID {league_id} no encontrada o inactiva'
                logger.error(error_msg)
                return {'status': 'error', 'message': error_msg}
            
            leagues = [league]
        else:
            # Scraping de todas las ligas activas
            leagues = League.objects.filter(is_active=True).select_related('category')
            
            if not leagues.exists():
                error_msg = 'No se encontraron ligas activas'
                logger.warning(error_msg)
                return {'status': 'error', 'message': error_msg}
        
        total_results = {
            'status': 'success',
            'leagues_processed': 0,
            'leagues_success': 0,
            'leagues_errors': 0,
            'total_matches': 0,
            'total_rounds': 0,
            'errors': []
        }
        
        for i, league in enumerate(leagues):
            category_name = league.category.name if league.category else 'Sin categoría'
            logger.info(f'[{i+1}/{len(leagues)}] Procesando resultados de {league.name} ({category_name})')
            
            try:
                scraper = FederationScraper(league)
                
                # Buscar endpoint de resultados
                results_endpoint = league.endpoints.filter(
                    endpoint_type='results',
                    is_active=True
                ).first()
                
                if not results_endpoint:
                    logger.warning(f'No se encontró endpoint de resultados activo para {league.name}')
                    total_results['leagues_processed'] += 1
                    total_results['leagues_errors'] += 1
                    total_results['errors'].append({
                        'league': league.name,
                        'error': 'No se encontró endpoint de resultados activo'
                    })
                    continue
                
                # NUEVO: Si no se especifica round_number, scrapear TODAS las jornadas
                if round_number is None:
                    logger.info(f'{league.name}: Scraping ALL rounds automatically')
                    result = scraper.scrape_all_results_rounds(delay=delay)
                    
                    if 'error' in result:
                        logger.error(f'{league.name} - Error: {result["error"]}')
                        total_results['leagues_errors'] += 1
                        total_results['errors'].append({
                            'league': league.name,
                            'error': result['error']
                        })
                    else:
                        matches_count = result.get('total_matches', 0)
                        rounds_count = result.get('rounds_with_data', 0)
                        total_results['total_matches'] += matches_count
                        total_results['total_rounds'] += rounds_count
                        total_results['leagues_success'] += 1
                        logger.info(f'{league.name}: {matches_count} matches from {rounds_count} rounds')
                
                else:
                    # LEGACY: Scrapear una jornada específica
                    logger.info(f'{league.name}: Scraping specific round {round_number}')
                    kwargs = {'round': round_number}
                    result = scraper.scrape_endpoint(results_endpoint, **kwargs)
                    
                    if 'error' in result:
                        logger.error(f'{league.name} - Error: {result["error"]}')
                        total_results['leagues_errors'] += 1
                        total_results['errors'].append({
                            'league': league.name,
                            'error': result['error']
                        })
                    else:
                        # Actualizar equipos si los hay
                        all_teams = {}
                        if 'teams' in result:
                            all_teams = scraper.update_teams(result['teams'])
                        
                        # Actualizar partidos en la base de datos
                        if 'matches' in result:
                            scraper.update_matches(result['matches'], all_teams)
                        
                        matches_count = len(result.get('matches', []))
                        total_results['total_matches'] += matches_count
                        total_results['total_rounds'] += 1
                        total_results['leagues_success'] += 1
                        logger.info(f'{league.name}: {matches_count} matches from round {round_number}')
                
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
            f"Scraping de resultados completado - Procesadas: {total_results['leagues_processed']}, "
            f"Exitosas: {total_results['leagues_success']}, "
            f"Con errores: {total_results['leagues_errors']}, "
            f"Jornadas: {total_results['total_rounds']}, "
            f"Partidos: {total_results['total_matches']}"
        )
        
        # Enviar email a admins si hay errores y las notificaciones están habilitadas
        if total_results['leagues_errors'] > 0 and settings.NOTIFICATION_EMAIL_ENABLED:
            subject = f"[I Love Voley] Errores en scraping automático de resultados"
            message = f"""
            Se han detectado errores durante el scraping automático de resultados:
            
            - Ligas procesadas: {total_results['leagues_processed']}
            - Ligas exitosas: {total_results['leagues_success']}
            - Ligas con errores: {total_results['leagues_errors']}
            - Jornadas procesadas: {total_results['total_rounds']}
            
            Partidos encontrados: {total_results['total_matches']}
            
            Errores detectados:
            {chr(10).join([f"- {e['league']}: {e['error']}" for e in total_results['errors'][:10]])}
            """
            
            try:
                mail_admins(subject, message, fail_silently=True)
            except Exception as e:
                logger.error(f"Error enviando email de notificación: {e}")
        
        return total_results
    
    except Exception as e:
        error_msg = f'Error general durante scraping de resultados: {str(e)}'
        logger.error(error_msg, exc_info=True)
        return {
            'status': 'error',
            'message': error_msg
        }


@shared_task(name='scrape_clubs', bind=True)
def scrape_clubs_task(self, match_teams=True, delay=1.0):
    """
    Ejecuta scraping de clubes desde voleibolib.net.
    
    Args:
        match_teams: Si es True, ejecuta matching automático de equipos con clubes
        delay: Delay entre requests en segundos (default: 1.0)
    
    Returns:
        dict: Estadísticas del scraping realizado
    """
    import requests
    from difflib import SequenceMatcher
    import unicodedata
    import re
    
    logger.info("Iniciando scraping de clubes desde voleibolib.net")
    
    def clean_string(value):
        """Limpia una cadena de texto"""
        if not value or value == 'null':
            return ''
        return str(value).strip()
    
    def clean_url(value):
        """Limpia y valida una URL"""
        if not value or value == 'null' or not str(value).strip():
            return ''
        url = str(value).strip()
        if url and not url.startswith(('http://', 'https://')):
            url = f'https://{url}'
        return url
    
    def normalize_name(name):
        """Normaliza un nombre para comparación"""
        if not name:
            return ''
        # Quitar acentos
        normalized = unicodedata.normalize('NFD', name)
        normalized = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
        # Convertir a mayúsculas y limpiar
        normalized = normalized.upper().strip()
        # Quitar caracteres especiales y espacios extra
        normalized = re.sub(r'[^\w\s]', ' ', normalized)
        normalized = ' '.join(normalized.split())
        return normalized
    
    def find_best_club_match(team, clubs):
        """Encuentra la mejor coincidencia entre un equipo y los clubes"""
        team_normalized = normalize_name(team.name)
        best_match = None
        best_similarity = 0
        
        for club in clubs:
            club_normalized = normalize_name(club.official_name)
            
            # Comparar nombre completo
            similarity = SequenceMatcher(None, team_normalized, club_normalized).ratio()
            
            # Comparar palabras clave
            team_words = set(team_normalized.split())
            club_words = set(club_normalized.split())
            
            common_words = team_words.intersection(club_words)
            if common_words:
                stopwords = {'club', 'volei', 'voley', 'voleibol', 'cv', 'esportiu', 'deportivo'}
                meaningful_common = common_words - stopwords
                
                if meaningful_common:
                    word_similarity = len(meaningful_common) / max(len(team_words), len(club_words))
                    similarity = max(similarity, word_similarity)
            
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = (club, similarity)
        
        return best_match if best_similarity > 0.3 else None
    
    try:
        # 1. Obtener lista de clubes
        url = 'https://www.voleibolib.net/JSON/get_clubes.asp'
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        clubs_data = response.json().get('items', [])
        
        logger.info(f'Encontrados {len(clubs_data)} clubes')
        
        created_count = 0
        updated_count = 0
        errors = []
        
        # 2. Procesar cada club
        for club_basic in clubs_data:
            club_id = club_basic['ID']
            club_name = club_basic['Nombre']
            
            try:
                # Obtener detalles del club
                detail_url = f'https://www.voleibolib.net/JSON/get_datos_club.asp?id={club_id}'
                detail_response = requests.get(detail_url, timeout=30)
                detail_response.raise_for_status()
                detail_data = detail_response.json()
                
                items = detail_data.get('items', [])
                if items:
                    club_data = items[0]
                    
                    # Crear o actualizar club
                    club, created = Club.objects.update_or_create(
                        federation_id=str(club_id),
                        defaults={
                            'official_name': clean_string(club_data.get('Nombre', '')),
                            'president': clean_string(club_data.get('Presidente', '')),
                            'address': clean_string(club_data.get('Direccion', '')),
                            'phone': clean_string(club_data.get('telefono', '')),
                            'email': clean_string(club_data.get('mail', '')),
                            'venue_name': clean_string(club_data.get('campo', '')),
                            'venue_address': clean_string(club_data.get('direccion_campo', '')),
                            'province': clean_string(club_data.get('provincia', '')),
                            'instagram': clean_url(club_data.get('instagram', '')),
                            'facebook': clean_url(club_data.get('facebook', '')),
                            'twitter': clean_url(club_data.get('twitter', '')),
                            'website': clean_url(club_data.get('url', '')),
                            'logo_url': f'https://voleibolib.federatio.com/fichas/clubes/{club_id}.jpg'
                        }
                    )
                    
                    if created:
                        created_count += 1
                        logger.info(f'Creado: {club.official_name}')
                    else:
                        updated_count += 1
                        logger.info(f'Actualizado: {club.official_name}')
                
                time.sleep(delay)
            
            except Exception as e:
                error_msg = f'Error procesando club {club_name} (ID: {club_id}): {str(e)}'
                logger.error(error_msg)
                errors.append(error_msg)
        
        # 3. Matching con equipos existentes
        matched_count = 0
        if match_teams:
            logger.info("Iniciando matching de equipos con clubes")
            teams_without_club = Team.objects.filter(club__isnull=True)
            clubs = Club.objects.all()
            
            for team in teams_without_club:
                best_match = find_best_club_match(team, clubs)
                
                if best_match:
                    club, similarity = best_match
                    if similarity > 0.55:  # Umbral de confianza
                        team.club = club
                        if not team.sponsor_name:
                            team.sponsor_name = team.name
                        team.save()
                        
                        matched_count += 1
                        logger.info(
                            f'Matched: {team.name} → {club.official_name} '
                            f'(confianza: {similarity:.2f})'
                        )
        
        summary = {
            'status': 'success',
            'clubs_created': created_count,
            'clubs_updated': updated_count,
            'teams_matched': matched_count,
            'errors': errors
        }
        
        logger.info(
            f"Scraping de clubes completado - "
            f"Creados: {created_count}, Actualizados: {updated_count}, "
            f"Equipos asociados: {matched_count}"
        )
        
        return summary
    
    except Exception as e:
        error_msg = f'Error durante scraping de clubes: {str(e)}'
        logger.error(error_msg, exc_info=True)
        return {
            'status': 'error',
            'message': error_msg
        }


@shared_task(name='handle_withdrawn_teams', bind=True)
def handle_withdrawn_teams_task(self, league_id=None, dry_run=False, reactivate_teams=False):
    """
    Gestiona equipos retirados y partidos asociados.
    
    Args:
        league_id: ID de la federación de la liga específica (opcional, si no se provee procesa todas)
        dry_run: Si es True, solo muestra qué haría sin hacer cambios (default: False)
        reactivate_teams: Si es True, reactiva equipos que aparecen de nuevo en federación (default: False)
    
    Returns:
        dict: Estadísticas de la operación realizada
    """
    logger.info("Iniciando gestión de equipos retirados")
    
    try:
        # Determinar ligas a procesar
        if league_id:
            try:
                leagues = [League.objects.get(federation_id=league_id, is_active=True)]
            except League.DoesNotExist:
                error_msg = f'Liga con ID {league_id} no encontrada o inactiva'
                logger.error(error_msg)
                return {'status': 'error', 'message': error_msg}
        else:
            leagues = League.objects.filter(is_active=True).select_related('category')
        
        if not leagues:
            error_msg = 'No se encontraron ligas activas para procesar'
            logger.warning(error_msg)
            return {'status': 'error', 'message': error_msg}
        
        total_results = {
            'status': 'success',
            'leagues_processed': 0,
            'teams_checked': 0,
            'teams_deactivated': 0,
            'teams_reactivated': 0,
            'matches_withdrawn': 0,
            'matches_reactivated': 0,
            'dry_run': dry_run,
            'details': []
        }
        
        for league in leagues:
            category_name = league.category.name if league.category else 'Sin categoría'
            logger.info(f'Procesando {league.name} ({category_name})')
            
            league_stats = {
                'league_name': league.name,
                'teams_checked': 0,
                'teams_deactivated': 0,
                'teams_reactivated': 0,
                'matches_withdrawn': 0,
                'matches_reactivated': 0,
                'inactive_teams': [],
                'reactivated_teams': []
            }
            
            # Obtener todos los equipos que participan en esta liga
            teams_in_league = Team.objects.filter(
                django_models.Q(home_matches__league=league) | django_models.Q(away_matches__league=league)
            ).distinct()
            
            league_stats['teams_checked'] = teams_in_league.count()
            
            # Verificar equipos inactivos y sus partidos
            for team in teams_in_league:
                if not team.is_active:
                    league_stats['inactive_teams'].append({
                        'name': team.name,
                        'federation_id': team.federation_id
                    })
                    
                    # Contar partidos afectados
                    affected_matches = Match.objects.filter(
                        league=league,
                        status__in=['scheduled', 'postponed']
                    ).filter(
                        django_models.Q(home_team=team) | django_models.Q(away_team=team)
                    )
                    
                    for match in affected_matches:
                        if not dry_run and match.status != 'withdrawn':
                            match.status = 'withdrawn'
                            match.save()
                            league_stats['matches_withdrawn'] += 1
                        elif dry_run and match.status != 'withdrawn':
                            league_stats['matches_withdrawn'] += 1
            
            # Si se solicita reactivación, buscar equipos que podrían reactivarse
            if reactivate_teams:
                inactive_teams = teams_in_league.filter(is_active=False)
                
                for team in inactive_teams:
                    # Aquí podrías implementar lógica para verificar si el equipo
                    # ha vuelto a aparecer en la federación
                    # Por simplicidad, por ahora solo reportamos los equipos inactivos
                    pass
            
            total_results['teams_checked'] += league_stats['teams_checked']
            total_results['teams_deactivated'] += len(league_stats['inactive_teams'])
            total_results['matches_withdrawn'] += league_stats['matches_withdrawn']
            total_results['leagues_processed'] += 1
            total_results['details'].append(league_stats)
            
            if league_stats['inactive_teams']:
                logger.warning(
                    f"{league.name}: {len(league_stats['inactive_teams'])} equipos inactivos, "
                    f"{league_stats['matches_withdrawn']} partidos marcados como retirados"
                )
            else:
                logger.info(f"{league.name}: No se encontraron equipos inactivos")
        
        # Log resumen final
        action_word = "Se marcarían" if dry_run else "Se marcaron"
        logger.info(
            f"Gestión de equipos retirados completada - "
            f"Ligas: {total_results['leagues_processed']}, "
            f"Equipos verificados: {total_results['teams_checked']}, "
            f"Equipos inactivos: {total_results['teams_deactivated']}, "
            f"{action_word} {total_results['matches_withdrawn']} partidos como retirados"
        )
        
        # Enviar email a admins si hay equipos inactivos y las notificaciones están habilitadas
        if total_results['teams_deactivated'] > 0 and settings.NOTIFICATION_EMAIL_ENABLED and not dry_run:
            subject = f"[VideosVoley] Equipos retirados detectados"
            
            inactive_teams_details = []
            for detail in total_results['details']:
                if detail['inactive_teams']:
                    league_info = f"\n{detail['league_name']}:"
                    for team in detail['inactive_teams']:
                        league_info += f"\n  - {team['name']} (ID: {team['federation_id']})"
                    inactive_teams_details.append(league_info)
            
            message = f"""
            Se han detectado equipos retirados en el sistema:
            
            Resumen:
            - Ligas procesadas: {total_results['leagues_processed']}
            - Equipos verificados: {total_results['teams_checked']}
            - Equipos inactivos encontrados: {total_results['teams_deactivated']}
            - Partidos marcados como retirados: {total_results['matches_withdrawn']}
            
            Equipos inactivos por liga:
            {''.join(inactive_teams_details)}
            
            Los partidos de estos equipos han sido marcados como 'retirados' automáticamente.
            """
            
            try:
                mail_admins(subject, message, fail_silently=True)
                logger.info("Email de notificación enviado a administradores")
            except Exception as e:
                logger.error(f"Error enviando email de notificación: {e}")
        
        return total_results
    
    except Exception as e:
        error_msg = f'Error durante gestión de equipos retirados: {str(e)}'
        logger.error(error_msg, exc_info=True)
        return {
            'status': 'error',
            'message': error_msg
        }


@shared_task(name='scrape_teams', bind=False)
def scrape_teams_task(league_id, category_name, dry_run=False, delay=1.0):
    """
    Ejecuta scraping de equipos de una liga específica y los asigna a una categoría.
    
    Args:
        league_id: ID de la federación de la liga de donde extraer equipos
        category_name: Nombre de la categoría a asignar a los equipos
        dry_run: Si es True, simula la operación sin guardar cambios (default: False)
        delay: Tiempo de espera entre requests en segundos (default: 1.0)
    
    Returns:
        dict: Estadísticas del scraping realizado
    """
    from videosvoley.videos.models import Category
    
    logger.info(f"Iniciando scraping de equipos - Liga ID: {league_id}, Categoría: {category_name}")
    
    try:
        # Buscar o crear la categoría
        category = None
        category_created = False
        
        try:
            category = Category.objects.get(name=category_name)
            logger.info(f'Usando categoría existente: {category.name}')
        except Category.DoesNotExist:
            if dry_run:
                logger.info(f'[DRY RUN] Se crearía la categoría: {category_name}')
            else:
                category = Category.objects.create(
                    name=category_name,
                    description=f'Categoría creada automáticamente durante scraping de equipos',
                    is_active=True
                )
                category_created = True
                logger.info(f'Categoría creada: {category.name}')
        
        # Verificar si ya existe una liga con ese federation_id
        existing_league = League.objects.filter(federation_id=league_id).first()
        
        if existing_league:
            logger.info(f'Liga encontrada: {existing_league.name}')
            # Usar la categoría de la liga existente si coincide
            if existing_league.category and existing_league.category.name != category_name:
                logger.warning(
                    f'ADVERTENCIA: La liga existente tiene categoría "{existing_league.category.name}" '
                    f'pero se especificó "{category_name}". Se usará la especificada.'
                )
        else:
            logger.info(f'No se encontró liga con ID {league_id}. Se usará solo para scraping.')
        
        # Si existe una liga, usar esa; si no, crear una temporal
        if existing_league:
            # Usar liga existente
            scraper_league = existing_league
            logger.info(f'Usando liga existente: {scraper_league.name}')
        else:
            # Para equipos de ligas no registradas, usar la lógica del comando directo
            # Reutilizar la lógica del comando scrape_teams
            from django.core.management.base import CommandError
            from videosvoley.videos.management.commands.scrape_teams import Command as ScrapeTeamsCommand
            
            # Crear instancia del comando y ejecutar
            command = ScrapeTeamsCommand()
            
            # Simular argumentos del comando
            options = {
                'league_id': league_id,
                'category': category_name,
                'verbose': True,
                'dry_run': dry_run
            }
            
            try:
                # Capturar output del comando
                import io
                from contextlib import redirect_stdout, redirect_stderr
                
                stdout_capture = io.StringIO()
                stderr_capture = io.StringIO()
                
                with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                    command.handle(**options)
                
                # El comando maneja toda la lógica, solo devolvemos un resumen
                summary = {
                    'status': 'success',
                    'league_id': league_id,
                    'category_name': category_name,
                    'category_created': category_created,
                    'dry_run': dry_run,
                    'message': 'Scraping completado usando comando directo',
                    'command_output': stdout_capture.getvalue(),
                    'command_errors': stderr_capture.getvalue()
                }
                
                logger.info(f"Scraping de equipos completado usando comando directo")
                return summary
                
            except CommandError as e:
                logger.error(f"Error en comando de scraping: {e}")
                return {
                    'status': 'error',
                    'league_id': league_id,
                    'category_name': category_name,
                    'message': str(e)
                }
        
        logger.info(f'Iniciando scraping de equipos usando liga: {scraper_league.name}')
        if dry_run:
            logger.info('[MODO DRY RUN - No se guardarán cambios]')
        
        scraper = FederationScraper(scraper_league)
        
        # Rate limiting inicial
        time.sleep(delay)
        
        results = scraper.scrape_all_endpoints()
        
        summary = {
            'status': 'success',
            'league_id': league_id,
            'category_name': category_name,
            'category_created': category_created,
            'dry_run': dry_run,
            'teams_processed': 0,
            'teams_created': 0,
            'teams_updated': 0,
            'endpoints_processed': 0,
            'endpoints_success': 0,
            'endpoints_errors': 0,
            'errors': []
        }
        
        # Procesar todos los endpoints que contengan equipos
        for endpoint_type, data in results.items():
            summary['endpoints_processed'] += 1
            
            if 'error' in data:
                logger.error(f'{endpoint_type}: Error - {data["error"]}')
                summary['endpoints_errors'] += 1
                summary['errors'].append({
                    'endpoint': endpoint_type,
                    'error': data['error']
                })
                continue
            
            summary['endpoints_success'] += 1
            teams_data = data.get('teams', [])
            
            if not teams_data:
                logger.info(f'{endpoint_type}: No se encontraron equipos')
                continue
            
            logger.info(f'=== Procesando equipos de {endpoint_type} ===')
            
            for team_data in teams_data:
                summary['teams_processed'] += 1
                team_name = team_data.get('name', '').strip()
                team_federation_id = team_data.get('federation_id', '')
                
                if not team_name:
                    logger.warning(f'Equipo sin nombre válido encontrado: {team_data}')
                    continue
                
                logger.info(f'Procesando: {team_name}')
                
                if dry_run:
                    # En modo dry run, solo mostrar lo que se haría
                    existing = Team.objects.filter(federation_id=team_federation_id).first() if team_federation_id else None
                    if existing:
                        logger.info(f'  [DRY RUN] Se actualizaría: {existing.name} -> categoría {category_name}')
                        summary['teams_updated'] += 1
                    else:
                        logger.info(f'  [DRY RUN] Se crearía: {team_name} con categoría {category_name}')
                        summary['teams_created'] += 1
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
                        existing_team.name = team_name
                        updated = True
                    
                    if updated:
                        existing_team.save()
                        summary['teams_updated'] += 1
                        logger.info(f'  ✓ Actualizado: {existing_team.name}')
                    else:
                        logger.info(f'  - Sin cambios: {existing_team.name}')
                else:
                    # Crear nuevo equipo
                    new_team = Team.objects.create(
                        name=team_name,
                        federation_id=team_federation_id,
                        category=category,
                        is_active=True
                    )
                    summary['teams_created'] += 1
                    logger.info(f'  ✓ Creado: {new_team.name}')
                
                # Rate limiting entre equipos
                time.sleep(delay * 0.1)  # Delay más corto entre equipos
        
        # Si hay errores en todos los endpoints, marcar como error parcial
        if summary['endpoints_errors'] > 0 and summary['endpoints_success'] == 0:
            summary['status'] = 'error'
        elif summary['endpoints_errors'] > 0:
            summary['status'] = 'partial_success'
        
        # Log resumen final
        action_word = "Se procesarían" if dry_run else "Se procesaron"
        logger.info(
            f"Scraping de equipos completado - "
            f"Endpoints: {summary['endpoints_success']}/{summary['endpoints_processed']} exitosos, "
            f"{action_word} {summary['teams_processed']} equipos: "
            f"{summary['teams_created']} creados, {summary['teams_updated']} actualizados"
        )
        
        # Enviar email a admins si hay errores y las notificaciones están habilitadas
        if summary['endpoints_errors'] > 0 and settings.NOTIFICATION_EMAIL_ENABLED and not dry_run:
            subject = f"[VideosVoley] Errores en scraping automático de equipos"
            message = f"""
            Se han detectado errores durante el scraping automático de equipos:
            
            Liga ID: {league_id}
            Categoría: {category_name}
            
            - Endpoints procesados: {summary['endpoints_processed']}
            - Endpoints exitosos: {summary['endpoints_success']}
            - Endpoints con errores: {summary['endpoints_errors']}
            
            Equipos procesados: {summary['teams_processed']}
            - Equipos creados: {summary['teams_created']}
            - Equipos actualizados: {summary['teams_updated']}
            
            Errores detectados:
            {chr(10).join([f"- {e['endpoint']}: {e['error']}" for e in summary['errors']])}
            """
            
            try:
                mail_admins(subject, message, fail_silently=True)
                logger.info("Email de notificación enviado a administradores")
            except Exception as e:
                logger.error(f"Error enviando email de notificación: {e}")
        
        return summary
    
    except Exception as e:
        error_msg = f'Error durante scraping de equipos: {str(e)}'
        logger.error(error_msg, exc_info=True)
        return {
            'status': 'error',
            'league_id': league_id,
            'category_name': category_name,
            'message': error_msg
        }


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
            leagues = League.objects.filter(is_active=True).select_related('category')
            
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
            category_name = league.category.name if league.category else 'Sin categoría'
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
        
        from videosvoley.videos.scraping import FederationScraper
        
        # Usar endpoint específico para próximos partidos
        json_url = "https://www.voleibolib.net/JSON/get_partidos_desglose_competiciones.asp?op=1&fini=&ffin="
        
        # Obtener todas las ligas activas
        from videosvoley.videos.models import League
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
                logger.info(f"[{leagues_processed}/{leagues.count()}] Enriqueciendo partidos próximos de {league.name} ({league.category.name if league.category else 'Sin categoría'})")
                
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
    scrape_results = scrape_all_leagues_task.delay(
        round_number=round_number,
        category_filter=category_filter,
        delay=delay
    ).get()
    
    # 2. Ejecutar enriquecimiento JSON
    logger.info("=== FASE 2: Enriquecimiento JSON ===")
    enrich_results = enrich_matches_json_task.delay(delay=delay).get()
    
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

