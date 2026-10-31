"""Tareas de scraping desde la web de la federación (HTML/ASP)."""

import logging

from celery import chord, shared_task
from django.conf import settings
from django.db import models as django_models

from ilovevoley.core.email_utils import send_technical_alert
from ilovevoley.competitions.models import League, Match
from ilovevoley.competitions.scraping.federation import FederationScraper
from ilovevoley.teams.models import Club, Team

logger = logging.getLogger(__name__)

def _active_leagues(category_filter=None):
    leagues = League.objects.filter(is_active=True)
    if category_filter:
        leagues = leagues.filter(categories__name__icontains=category_filter).distinct()
    return leagues


def _mail_admins_on_errors(subject, message):
    """Retrocompatibilidad interna: redirige a send_technical_alert."""
    send_technical_alert(subject, message)


def _get_league(league_pk, empty_stats):
    """
    (league, None), o (None, stats_fallidas) si la liga no se puede cargar.

    Las tareas por liga forman el header de un chord: una excepción aquí lo dejaría
    sin callback (sin resumen, sin email y sin el enriquecimiento encadenado).
    """
    name = f'#{league_pk}'
    try:
        return League.objects.prefetch_related('categories').get(pk=league_pk), None
    except League.DoesNotExist:
        error = 'La liga ya no existe'
        logger.warning(f'{error}: {name}')
    except Exception as e:
        error = str(e)
        logger.error(f'No se pudo cargar la liga {name}: {e}', exc_info=True)
    failed = {**empty_stats, 'league': name, 'success': False,
              'errors': [{'league': name, 'endpoint': 'general', 'error': error}]}
    return None, failed


def build_scrape_all_leagues_workflow(round_number=None, category_filter=None, delay=2.0, then=None):
    """
    Un `scrape_league_stats` por liga más el callback que agrega y avisa a admins.

    La separación entre ligas es un `countdown` escalonado, no un `sleep`: el
    worker queda libre entre ligas. Techo: el rate limit solo espacia el arranque
    de cada liga; con varios workers pueden solaparse las ligas más lentas.
    `then`: firma que se encadena tras el resumen (p. ej. el enriquecimiento).

    Devuelve (workflow, n_ligas) o (None, 0) si no hay ligas.
    """
    league_ids = list(_active_leagues(category_filter).values_list('pk', flat=True))
    if not league_ids:
        return None, 0
    header = [
        scrape_league_stats_task.s(league_pk, round_number).set(countdown=i * delay)
        for i, league_pk in enumerate(league_ids)
    ]
    callback = scrape_leagues_summary_task.s()
    if then is not None:
        callback = callback | then
    return chord(header)(callback), len(league_ids)


@shared_task(name='scrape_all_leagues', bind=True)
def scrape_all_leagues_task(self, round_number=None, category_filter=None, delay=2.0):
    """
    Lanza el scraping de todas las ligas activas, una tarea por liga.

    Args:
        round_number: Jornada específica (opcional)
        category_filter: Filtrar solo ligas de una categoría específica (opcional)
        delay: Segundos entre el arranque de una liga y la siguiente (default: 2.0)

    Returns:
        dict: Ligas encoladas. Las estadísticas agregadas las devuelve
        `scrape_leagues_summary`, que también envía el email de errores.
    """
    logger.info("Iniciando tarea de scraping de todas las ligas activas")
    workflow, queued = build_scrape_all_leagues_workflow(round_number, category_filter, delay)
    if not workflow:
        error_msg = 'No se encontraron ligas activas'
        if category_filter:
            error_msg += f" de categoría '{category_filter}'"
        logger.warning(error_msg)
        return {'status': 'error', 'message': error_msg}
    return {'status': 'queued', 'leagues_queued': queued}


@shared_task(name='scrape_league_stats', bind=True)
def scrape_league_stats_task(self, league_pk, round_number=None):
    """Scrapea todos los endpoints de una liga y devuelve sus estadísticas."""
    league, failed = _get_league(league_pk, {'teams': 0, 'matches': 0, 'standings': 0})
    if failed:
        return failed
    category_name = ', '.join(c.name for c in league.categories.all()) or 'Sin categoría'
    logger.info(f'Procesando {league.name} ({category_name})')

    stats = {'league': league.name, 'success': True, 'teams': 0, 'matches': 0, 'standings': 0, 'errors': []}
    try:
        results = FederationScraper(league).scrape_all_endpoints(round=round_number)
        for endpoint_type, data in results.items():
            if 'error' in data:
                logger.error(f'{league.name} - {endpoint_type}: {data["error"]}')
                stats['success'] = False
                stats['errors'].append({'league': league.name, 'endpoint': endpoint_type, 'error': data['error']})
            else:
                stats['teams'] += len(data.get('teams', []))
                stats['matches'] += len(data.get('matches', []))
                stats['standings'] += len(data.get('standings', []))
        if stats['success']:
            logger.info(
                f'{league.name}: {stats["teams"]} equipos, '
                f'{stats["matches"]} partidos, {stats["standings"]} clasificaciones'
            )
    except Exception as e:
        stats['success'] = False
        logger.error(f'Error crítico en {league.name}: {e}', exc_info=True)
        stats['errors'].append({'league': league.name, 'endpoint': 'general', 'error': str(e)})
    return stats


@shared_task(name='scrape_leagues_summary', bind=True)
def scrape_leagues_summary_task(self, league_stats):
    """Callback del chord: agrega las estadísticas por liga y avisa a admins si hubo errores."""
    total_results = {
        'status': 'success',
        'leagues_processed': len(league_stats),
        'leagues_success': sum(1 for s in league_stats if s['success']),
        'leagues_errors': sum(1 for s in league_stats if not s['success']),
        'total_teams': sum(s['teams'] for s in league_stats),
        'total_matches': sum(s['matches'] for s in league_stats),
        'total_standings': sum(s['standings'] for s in league_stats),
        'errors': [e for s in league_stats for e in s['errors']],
    }

    # Log resumen final
    logger.info(
        f"Scraping completado - Procesadas: {total_results['leagues_processed']}, "
        f"Exitosas: {total_results['leagues_success']}, "
        f"Con errores: {total_results['leagues_errors']}"
    )
    
    if total_results['leagues_errors'] > 0:
        subject = "[I Love Voley] Errores en scraping automático de ligas"
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
        send_technical_alert(subject, message)
    
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
    
    except Exception:
        # Relanzar: Celery marca FAILURE y Sentry captura el traceback
        raise


def _persist_endpoint_result(scraper, result):
    """Guarda equipos y partidos de un resultado de endpoint y devuelve cuántos partidos trae."""
    all_teams = scraper.update_teams(result['teams']) if 'teams' in result else {}
    if 'matches' in result:
        scraper.update_matches(result['matches'], all_teams)
    return len(result.get('matches', []))


def _calendar_league_stats(league):
    stats = {'league': league.name, 'success': True, 'matches': 0, 'rounds': 0, 'errors': []}
    try:
        scraper = FederationScraper(league)
        endpoint = league.endpoints.filter(endpoint_type='calendar', is_active=True).first()
        if not endpoint:
            logger.warning(f'No se encontró endpoint de calendario activo para {league.name}')
            error = 'No se encontró endpoint de calendario activo'
        else:
            result = scraper.scrape_endpoint(endpoint)
            error = result.get('error')
            if not error:
                stats['matches'] = _persist_endpoint_result(scraper, result)
                logger.info(f'{league.name}: {stats["matches"]} partidos guardados en el calendario')
    except Exception as e:
        logger.error(f'Error crítico en {league.name}: {e}', exc_info=True)
        error = str(e)
    if error:
        logger.error(f'{league.name} - Error: {error}')
        stats['success'] = False
        stats['errors'].append({'league': league.name, 'error': error})
    return stats


def _results_league_stats(league, round_number, delay):
    stats = {'league': league.name, 'success': True, 'matches': 0, 'rounds': 0, 'errors': []}
    try:
        scraper = FederationScraper(league)
        endpoint = league.endpoints.filter(endpoint_type='results', is_active=True).first()
        if not endpoint:
            logger.warning(f'No se encontró endpoint de resultados activo para {league.name}')
            error = 'No se encontró endpoint de resultados activo'
        elif round_number is None:
            result = scraper.scrape_all_results_rounds(delay=delay)
            error = result.get('error')
            if not error:
                stats['matches'] = result.get('total_matches', 0)
                stats['rounds'] = result.get('rounds_with_data', 0)
        else:
            result = scraper.scrape_endpoint(endpoint, round=round_number)
            error = result.get('error')
            if not error:
                stats['matches'] = _persist_endpoint_result(scraper, result)
                stats['rounds'] = 1
        if not error:
            logger.info(f'{league.name}: {stats["matches"]} matches from {stats["rounds"]} rounds')
    except Exception as e:
        logger.error(f'Error crítico en {league.name}: {e}', exc_info=True)
        error = str(e)
    if error:
        logger.error(f'{league.name} - Error: {error}')
        stats['success'] = False
        stats['errors'].append({'league': league.name, 'error': error})
    return stats


def _summarize_league_stats(league_stats):
    return {
        'status': 'success',
        'leagues_processed': len(league_stats),
        'leagues_success': sum(1 for s in league_stats if s['success']),
        'leagues_errors': sum(1 for s in league_stats if not s['success']),
        'total_matches': sum(s['matches'] for s in league_stats),
        'total_rounds': sum(s['rounds'] for s in league_stats),
        'errors': [e for s in league_stats for e in s['errors']],
    }


def _target_leagues(league_id):
    """(ligas, error): la liga pedida por federation_id o todas las activas."""
    if league_id:
        league = League.objects.filter(federation_id=league_id, is_active=True).first()
        if not league:
            return [], f'Liga con ID {league_id} no encontrada o inactiva'
        return [league], None
    leagues = list(League.objects.filter(is_active=True))
    return leagues, (None if leagues else 'No se encontraron ligas activas')


@shared_task(name='scrape_calendar_league', bind=True)
def scrape_calendar_league_task(self, league_pk):
    """Scrapea el calendario de una liga (parte del chord de scrape_calendar)."""
    league, failed = _get_league(league_pk, {'matches': 0, 'rounds': 0})
    return failed or _calendar_league_stats(league)


@shared_task(name='scrape_results_league', bind=True)
def scrape_results_league_task(self, league_pk, round_number=None, delay=2.0):
    """Scrapea los resultados de una liga (parte del chord de scrape_results)."""
    league, failed = _get_league(league_pk, {'matches': 0, 'rounds': 0})
    return failed or _results_league_stats(league, round_number, delay)


@shared_task(name='scrape_endpoint_summary', bind=True)
def scrape_endpoint_summary_task(self, league_stats, kind):
    """Callback del chord: agrega las estadísticas por liga y avisa a admins si hubo errores.

    `kind`: 'calendario' o 'resultados', para el log y el asunto del email.
    """
    total_results = _summarize_league_stats(league_stats)
    logger.info(
        f"Scraping de {kind} completado - Procesadas: {total_results['leagues_processed']}, "
        f"Exitosas: {total_results['leagues_success']}, "
        f"Con errores: {total_results['leagues_errors']}, "
        f"Jornadas: {total_results['total_rounds']}, "
        f"Partidos: {total_results['total_matches']}"
    )
    if total_results['leagues_errors'] > 0:
        subject = f"[I Love Voley] Errores en scraping automático de {kind}"
        message = f"""
        Se han detectado errores durante el scraping automático de {kind}:

        - Ligas procesadas: {total_results['leagues_processed']}
        - Ligas exitosas: {total_results['leagues_success']}
        - Ligas con errores: {total_results['leagues_errors']}
        - Jornadas procesadas: {total_results['total_rounds']}

        Partidos encontrados: {total_results['total_matches']}

        Errores detectados:
        {chr(10).join([f"- {e['league']}: {e['error']}" for e in total_results['errors'][:10]])}
        """
        send_technical_alert(subject, message)
    return total_results


def _fan_out_leagues(task, league_pks, delay, kind, *args):
    """Una tarea por liga con arranque escalonado por `countdown` (sin sleep en el worker, #601)."""
    header = [task.s(pk, *args).set(countdown=i * delay) for i, pk in enumerate(league_pks)]
    return chord(header)(scrape_endpoint_summary_task.s(kind))


@shared_task(name='scrape_calendar', bind=True)
def scrape_calendar_task(self, league_id=None, delay=2.0):
    """
    Lanza el scraping del calendario de partidos, una tarea por liga.

    Con league_id scrapea solo esa liga, en línea. Sin él, encola todas las
    ligas activas y el resumen (y el email de errores) lo produce
    `scrape_endpoint_summary`.

    Args:
        league_id: ID de la federación de la liga (opcional)
        delay: Segundos entre el arranque de una liga y la siguiente (default: 2.0)
    """
    logger.info("Iniciando scraping de calendario de partidos")
    leagues, error_msg = _target_leagues(league_id)
    if error_msg:
        logger.error(error_msg)
        return {'status': 'error', 'message': error_msg}
    if league_id:
        return _summarize_league_stats([_calendar_league_stats(leagues[0])])
    _fan_out_leagues(scrape_calendar_league_task, [league.pk for league in leagues], delay, 'calendario')
    return {'status': 'queued', 'leagues_queued': len(leagues)}


@shared_task(name='scrape_results', bind=True)
def scrape_results_task(self, league_id=None, round_number=None, delay=2.0):
    """
    Lanza el scraping de resultados de partidos, una tarea por liga.

    Con league_id scrapea solo esa liga, en línea. Sin él, encola todas las
    ligas activas. Sin round_number scrapea todas las jornadas de cada liga.

    Args:
        league_id: ID de la federación de la liga (opcional)
        round_number: Jornada específica a scrapear (opcional)
        delay: Segundos entre ligas (arranque) y entre jornadas de una liga (default: 2.0)
    """
    logger.info("Iniciando scraping de resultados de partidos")
    leagues, error_msg = _target_leagues(league_id)
    if error_msg:
        logger.error(error_msg)
        return {'status': 'error', 'message': error_msg}
    if league_id:
        return _summarize_league_stats([_results_league_stats(leagues[0], round_number, delay)])
    league_pks = [league.pk for league in leagues]
    _fan_out_leagues(scrape_results_league_task, league_pks, delay, 'resultados', round_number, delay)
    return {'status': 'queued', 'leagues_queued': len(leagues)}


def _clean_string(value):
    """Limpia una cadena de texto"""
    if not value or value == 'null':
        return ''
    return str(value).strip()


def _clean_url(value):
    """Limpia y valida una URL"""
    if not value or value == 'null' or not str(value).strip():
        return ''
    url = str(value).strip()
    if url and not url.startswith(('http://', 'https://')):
        url = f'https://{url}'
    return url


@shared_task(name='scrape_club', bind=True)
def scrape_club_task(self, club_id, club_name):
    """Descarga el detalle de un club y lo crea o actualiza (parte del chord de scrape_clubs)."""
    import requests

    from ilovevoley.teams.services import cache_logo

    try:
        detail_url = f'https://www.voleibolib.net/JSON/get_datos_club.asp?id={club_id}'
        detail_response = requests.get(detail_url, timeout=30)
        detail_response.raise_for_status()
        items = detail_response.json().get('items', [])
        if not items:
            return {'created': None, 'error': None}
        club_data = items[0]

        club, created = Club.objects.update_or_create(
            federation_id=str(club_id),
            defaults={
                'official_name': _clean_string(club_data.get('Nombre', '')),
                'president': _clean_string(club_data.get('Presidente', '')),
                'address': _clean_string(club_data.get('Direccion', '')),
                'phone': _clean_string(club_data.get('telefono', '')),
                'email': _clean_string(club_data.get('mail', '')),
                'venue_name': _clean_string(club_data.get('campo', '')),
                'venue_address': _clean_string(club_data.get('direccion_campo', '')),
                'municipality': _clean_string(club_data.get('municipio', '')),
                'province': _clean_string(club_data.get('provincia', '')),
                'instagram': _clean_url(club_data.get('instagram', '')),
                'facebook': _clean_url(club_data.get('facebook', '')),
                'twitter': _clean_url(club_data.get('twitter', '')),
                'website': _clean_url(club_data.get('url', '')),
                'logo_url': f'https://voleibolib.federatio.com/fichas/clubes/{club_id}.jpg'
            }
        )
        if not club.logo:
            cache_logo(club)
        logger.info(f'{"Creado" if created else "Actualizado"}: {club.official_name}')
        return {'created': created, 'error': None}
    except Exception as e:
        error_msg = f'Error procesando club {club_name} (ID: {club_id}): {str(e)}'
        logger.error(error_msg, exc_info=True)
        return {'created': None, 'error': error_msg}


@shared_task(name='scrape_clubs_summary', bind=True)
def scrape_clubs_summary_task(self, club_results, match_teams=True):
    """Callback del chord: agrega los clubes y, con todos ya guardados, asocia equipos a clubes."""
    created_count = sum(1 for r in club_results if r['created'] is True)
    updated_count = sum(1 for r in club_results if r['created'] is False)
    errors = [r['error'] for r in club_results if r['error']]

    matched_count = 0
    if match_teams:
        logger.info("Iniciando matching de equipos con clubes")
        from ilovevoley.teams.services import resolve_team_clubs
        team_clubs = resolve_team_clubs(Match, Club)

        for team in Team.objects.filter(club__isnull=True, pk__in=team_clubs):
            team.club = team_clubs[team.pk]
            if not team.sponsor_name:
                team.sponsor_name = team.name
            team.save()
            matched_count += 1

    logger.info(
        f"Scraping de clubes completado - "
        f"Creados: {created_count}, Actualizados: {updated_count}, "
        f"Equipos asociados: {matched_count}"
    )
    return {
        'status': 'success',
        'clubs_created': created_count,
        'clubs_updated': updated_count,
        'teams_matched': matched_count,
        'errors': errors
    }


@shared_task(name='scrape_clubs', bind=True)
def scrape_clubs_task(self, match_teams=True, delay=1.0):
    """
    Lanza el scraping de clubes desde voleibolib.net, una tarea por club.

    El arranque de cada club se escalona por `countdown` en vez de dormir en el
    worker (#601); `scrape_clubs_summary` agrega y asocia equipos a clubes.

    Args:
        match_teams: Si es True, ejecuta matching automático de equipos con clubes
        delay: Segundos entre el arranque de un club y el siguiente (default: 1.0)

    Returns:
        dict: Clubes encolados
    """
    import requests

    logger.info("Iniciando scraping de clubes desde voleibolib.net")
    try:
        response = requests.get('https://www.voleibolib.net/JSON/get_clubes.asp', timeout=30)
        response.raise_for_status()
        clubs_data = response.json().get('items', [])
        logger.info(f'Encontrados {len(clubs_data)} clubes')
        if not clubs_data:
            return {'status': 'error', 'message': 'La federación no devolvió clubes'}

        header = [
            scrape_club_task.s(club['ID'], club['Nombre']).set(countdown=i * delay)
            for i, club in enumerate(clubs_data)
        ]
        chord(header)(scrape_clubs_summary_task.s(match_teams=match_teams))
        return {'status': 'queued', 'clubs_queued': len(header)}

    except Exception:
        # Relanzar: Celery marca FAILURE y Sentry captura el traceback
        raise


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
            leagues = League.objects.filter(is_active=True).prefetch_related('categories')
        
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
            # Obtener nombres de todas las categorías
            categories = league.categories.all()
            category_name = ', '.join([c.name for c in categories]) if categories else 'Sin categoría'
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
            
            send_technical_alert(subject, message)
        
        return total_results
    
    except Exception:
        # Relanzar: Celery marca FAILURE y Sentry captura el traceback
        raise


@shared_task(name='scrape_teams', bind=False)
def scrape_teams_task(league_id, category_name, dry_run=False, delay=1.0):
    """
    Ejecuta scraping de equipos de una liga específica y los asigna a una categoría.
    
    Args:
        league_id: ID de la federación de la liga de donde extraer equipos
        category_name: Nombre de la categoría a asignar a los equipos
        dry_run: Si es True, simula la operación sin guardar cambios (default: False)
        delay: Sin efecto: antes dormía el worker sin que hubiera requests que espaciar (#601);
            se conserva para no romper llamadas existentes
    
    Returns:
        dict: Estadísticas del scraping realizado
    """
    from ilovevoley.core.models import Category
    
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
            # Verificar si la categoría ya está asignada a la liga
            existing_categories = existing_league.categories.all()
            if existing_categories and category not in existing_categories:
                existing_cat_names = ', '.join([c.name for c in existing_categories])
                logger.warning(
                    f'ADVERTENCIA: La liga existente tiene categorías "{existing_cat_names}" '
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
            from ilovevoley.videos.management.commands.scrape_teams import Command as ScrapeTeamsCommand
            
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
                        # Solo actualizar el nombre si no es un duplicado por nombre normalizado
                        from ilovevoley.videos.utils import normalize_team_name
                        if normalize_team_name(existing_team.name) != normalize_team_name(team_name):
                            existing_team.name = team_name
                            updated = True
                        else:
                            logger.info(f'  - Variación de nombre detectada: "{existing_team.name}" vs "{team_name}"')
                    
                    if updated:
                        existing_team.save()
                        summary['teams_updated'] += 1
                        logger.info(f'  ✓ Actualizado: {existing_team.name}')
                    else:
                        logger.info(f'  - Sin cambios: {existing_team.name}')
                else:
                    # Buscar duplicado por nombre normalizado antes de crear
                    from ilovevoley.videos.utils import find_duplicate_team_by_name
                    duplicate_team = find_duplicate_team_by_name(team_name, category=category)
                    
                    if duplicate_team:
                        # Actualizar el equipo duplicado con el nuevo federation_id
                        duplicate_team.federation_id = team_federation_id
                        duplicate_team.is_active = True
                        duplicate_team.save()
                        summary['teams_updated'] += 1
                        logger.info(f'  ✓ Duplicado encontrado y actualizado: "{duplicate_team.name}" (federation_id: {team_federation_id})')
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
            
            send_technical_alert(subject, message)
        
        return summary
    
    except Exception:
        # Relanzar: Celery marca FAILURE y Sentry captura el traceback
        raise

__all__ = [
    'scrape_all_leagues_task',
    'scrape_league_stats_task',
    'scrape_leagues_summary_task',
    'build_scrape_all_leagues_workflow',
    'scrape_league_task',
    'scrape_calendar_task',
    'scrape_calendar_league_task',
    'scrape_results_league_task',
    'scrape_endpoint_summary_task',
    'scrape_results_task',
    'scrape_clubs_task',
    'scrape_club_task',
    'scrape_clubs_summary_task',
    'handle_withdrawn_teams_task',
    'scrape_teams_task',
]
