import logging
from datetime import datetime, timedelta
from collections import defaultdict
from django.http import Http404, HttpResponseNotFound
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.core.cache import cache
from django.shortcuts import redirect
from .email_utils import get_admin_emails
from .tenant_utils import get_organization_by_slug


logger = logging.getLogger(__name__)

TENANT_EXEMPT_PREFIXES = (
    '/videos/calendario/suscripcion/',
)


class TenantMiddleware:
    """
    Resuelve el tenant (Organization) a partir del subdominio del Host header
    y lo pone en request.tenant.

    Modo passthrough (Fase 1): si no hay subdominio reconocido, asigna Sant Josep
    para que ilovevoley.es siga funcionando. En Fase 2 se elimina el passthrough.
    """

    PASSTHROUGH = False

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.META.get('HTTP_HOST', '').split(':')[0]
        parts = host.split('.')
        root_domain = '.'.join(parts[-2:]) if len(parts) >= 2 else host

        if host == root_domain:
            if self.PASSTHROUGH:
                request.tenant = get_organization_by_slug('santjosep')
            else:
                request.tenant = None
        else:
            subdomain = parts[0]
            request.tenant = get_organization_by_slug(subdomain)
            if request.tenant is None:
                if self.PASSTHROUGH:
                    request.tenant = get_organization_by_slug('santjosep')
                else:
                    return HttpResponseNotFound()

        if request.tenant is None and request.path.startswith('/videos/'):
            if not any(request.path.startswith(prefix) for prefix in TENANT_EXEMPT_PREFIXES):
                return redirect('landing')

        return self.get_response(request)


class Error404TrackingMiddleware:
    """
    Middleware para trackear errores 404 y enviar reportes por email
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        response = self.get_response(request)
        
        # Capturar errores 404
        if response.status_code == 404:
            self.log_404_error(request)
            
        return response
    
    def log_404_error(self, request):
        """
        Registra un error 404 en cache para reporte posterior
        """
        try:
            # Obtener información del error
            error_data = {
                'url': request.get_full_path(),
                'method': request.method,
                'ip': self.get_client_ip(request),
                'user_agent': request.META.get('HTTP_USER_AGENT', '')[:200],
                'referer': request.META.get('HTTP_REFERER', ''),
                'timestamp': datetime.now().isoformat(),
                'user': str(request.user) if request.user.is_authenticated else 'Anonymous',
            }
            
            # Guardar en cache para reporte diario
            cache_key = f"404_errors_{datetime.now().strftime('%Y%m%d')}"
            errors_today = cache.get(cache_key, [])
            errors_today.append(error_data)
            
            # Mantener solo últimos 100 errores del día
            if len(errors_today) > 100:
                errors_today = errors_today[-100:]
            
            # Guardar por 48 horas
            cache.set(cache_key, errors_today, 60 * 60 * 48)
            
            logger.warning(f"404 Error: {error_data['url']} from {error_data['ip']}")
            
        except Exception as e:
            logger.error(f"Error logging 404: {str(e)}")
    
    def get_client_ip(self, request):
        """
        Obtiene la IP real del cliente
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


def send_404_daily_report():
    """
    Función para enviar reporte diario de errores 404
    Debe ser llamada por una tarea programada (cron, celery, etc.)
    """
    if not settings.EMAIL_NOTIFICATIONS.get('error_404_daily', False):
        return False
    
    admin_emails = get_admin_emails()
    if not settings.NOTIFICATION_EMAIL_ENABLED or not admin_emails:
        return False
    
    try:
        # Obtener errores de ayer
        yesterday = datetime.now() - timedelta(days=1)
        cache_key = f"404_errors_{yesterday.strftime('%Y%m%d')}"
        errors = cache.get(cache_key, [])
        
        if not errors:
            return False  # No hay errores que reportar
        
        # Agrupar errores por URL
        grouped_errors = defaultdict(list)
        for error in errors:
            grouped_errors[error['url']].append(error)
        
        # Preparar estadísticas
        total_errors = len(errors)
        unique_urls = len(grouped_errors)
        top_errors = sorted(
            grouped_errors.items(), 
            key=lambda x: len(x[1]), 
            reverse=True
        )[:10]
        
        # Preparar contexto para email
        context = {
            'date': yesterday.strftime('%d/%m/%Y'),
            'total_errors': total_errors,
            'unique_urls': unique_urls,
            'top_errors': top_errors,
            'site_name': 'I Love Voley',
        }
        
        # Enviar email
        html_message = render_to_string('emails/404_daily_report.html', context)
        plain_message = strip_tags(html_message)
        
        send_mail(
            subject=f'Reporte diario de errores 404 - {yesterday.strftime("%d/%m/%Y")}',
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=admin_emails,
            html_message=html_message,
            fail_silently=False,
        )
        
        logger.info(f"Reporte 404 enviado: {total_errors} errores")
        return True
        
    except Exception as e:
        logger.error(f"Error enviando reporte 404: {str(e)}")
        return False


def send_404_immediate_alert(request, threshold=10):
    """
    Envía alerta inmediata si hay muchos 404s en poco tiempo
    """
    if not settings.NOTIFICATION_EMAIL_ENABLED:
        return False
    
    try:
        admin_emails = get_admin_emails()
        if not admin_emails:
            return False
            
        # Contar errores en la última hora
        cache_key = f"404_count_{datetime.now().strftime('%Y%m%d_%H')}"
        current_count = cache.get(cache_key, 0) + 1
        cache.set(cache_key, current_count, 60 * 60)  # 1 hora
        
        # Si supera el umbral, enviar alerta
        if current_count == threshold:  # Solo enviar una vez por hora
            from ilovevoley.core.tasks import send_404_immediate_alert_task

            send_404_immediate_alert_task.delay(
                current_count,
                datetime.now().strftime('%H:00'),
                request.get_full_path(),
                admin_emails,
            )
            logger.warning(f"Alerta 404 encolada: {current_count} errores")
            return True
            
    except Exception as e:
        logger.error(f"Error enviando alerta 404: {str(e)}")
        return False
