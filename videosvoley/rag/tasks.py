import logging
from celery import shared_task
from django.core.management import call_command
from django.core.mail import mail_admins
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def incremental_reindex_task(self):
    """
    Tarea periódica para reindexar documentos de forma incremental
    """
    try:
        logger.info("Iniciando reindexación incremental automática")
        
        # Ejecutar indexación incremental para todos los tipos
        call_command(
            'index_documents',
            '--source-type', 'all',
            '--incremental',
            verbosity=1
        )
        
        logger.info("Reindexación incremental completada exitosamente")
        
        return {
            'status': 'success',
            'message': 'Reindexación incremental completada'
        }
        
    except Exception as exc:
        logger.error(f"Error en reindexación incremental: {exc}")
        
        # Enviar email a admins si está habilitado
        if getattr(settings, 'NOTIFICATION_EMAIL_ENABLED', False):
            try:
                mail_admins(
                    subject='Error en Reindexación RAG Automática',
                    message=f"""
Error durante la reindexación incremental automática del sistema RAG:

Error: {str(exc)}

Task ID: {self.request.id}
                    """,
                    fail_silently=True
                )
            except Exception as email_error:
                logger.error(f"Error enviando email de notificación: {email_error}")
        
        # Re-raise para que Celery marque la tarea como fallida
        raise self.retry(exc=exc, countdown=300, max_retries=3)


@shared_task(bind=True)
def full_reindex_task(self, source_types=None, limit=None):
    """
    Tarea para reindexación completa (forzada)
    
    Args:
        source_types: Lista de tipos a reindexar ['match', 'standing', etc.] o None para todos
        limit: Límite de elementos a procesar por tipo
    """
    try:
        logger.info(f"Iniciando reindexación completa - tipos: {source_types}, límite: {limit}")
        
        if source_types is None:
            source_types = ['match', 'standing', 'video', 'image', 'league']
        
        results = {}
        
        for source_type in source_types:
            try:
                logger.info(f"Reindexando {source_type}...")
                
                cmd_args = [
                    'index_documents',
                    '--source-type', source_type,
                    '--force'
                ]
                
                if limit:
                    cmd_args.extend(['--limit', str(limit)])
                
                call_command(*cmd_args, verbosity=1)
                
                results[source_type] = 'success'
                logger.info(f"Reindexación de {source_type} completada")
                
            except Exception as source_error:
                logger.error(f"Error reindexando {source_type}: {source_error}")
                results[source_type] = f'error: {str(source_error)}'
        
        logger.info("Reindexación completa finalizada")
        
        return {
            'status': 'completed',
            'results': results
        }
        
    except Exception as exc:
        logger.error(f"Error en reindexación completa: {exc}")
        
        if getattr(settings, 'NOTIFICATION_EMAIL_ENABLED', False):
            try:
                mail_admins(
                    subject='Error en Reindexación RAG Completa',
                    message=f"""
Error durante la reindexación completa del sistema RAG:

Error: {str(exc)}
Tipos solicitados: {source_types}
Límite: {limit}

Task ID: {self.request.id}
                    """,
                    fail_silently=True
                )
            except Exception as email_error:
                logger.error(f"Error enviando email de notificación: {email_error}")
        
        raise self.retry(exc=exc, countdown=600, max_retries=2)


@shared_task
def reindex_after_scraping_task(leagues_scraped=None):
    """
    Tarea que se ejecuta automáticamente después del scraping
    para mantener el RAG actualizado
    
    Args:
        leagues_scraped: Lista de IDs de ligas que fueron scrapeadas
    """
    try:
        logger.info(f"Iniciando reindexación post-scraping para ligas: {leagues_scraped}")
        
        # Reindexar partidos y clasificaciones (datos que cambian con scraping)
        call_command(
            'index_documents',
            '--source-type', 'match',
            '--incremental',
            verbosity=1
        )
        
        call_command(
            'index_documents',
            '--source-type', 'standing',
            '--force',  # Las clasificaciones siempre necesitan update completo
            verbosity=1
        )
        
        logger.info("Reindexación post-scraping completada")
        
        return {
            'status': 'success',
            'message': f'RAG actualizado después de scraping de ligas: {leagues_scraped}'
        }
        
    except Exception as exc:
        logger.error(f"Error en reindexación post-scraping: {exc}")
        return {
            'status': 'error',
            'message': str(exc)
        }