import ipaddress
import logging
import re
from urllib.parse import urlsplit, urlunsplit
from datetime import datetime, timedelta
from collections import defaultdict
from django.http import Http404, HttpResponseNotFound
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.csp import CSP
from django.utils.html import strip_tags
from django.core.cache import cache
from django.shortcuts import redirect
from .email_utils import get_admin_emails
from .tenant_utils import get_organization_by_slug


logger = logging.getLogger(__name__)

# Patrones para sanitizar tokens y credenciales sensibles en URLs
SENSITIVE_URL_PATTERNS = [
    (re.compile(r'(/moderate/(?:user|image)/)[^/]+(/?)'), r'\1[REDACTED]\2'),
    (re.compile(r'(/calendario/suscripcion/)[^/]+(/?)'), r'\1[REDACTED]\2'),
    (re.compile(r'(/accounts/password/reset/key/)[^/]+(/?)'), r'\1[REDACTED]\2'),
    (re.compile(r'(/accounts/confirm-email/)[^/]+(/?)'), r'\1[REDACTED]\2'),
    (re.compile(r'(/p/partido/)[^/]+(/?)'), r'\1[REDACTED]\2'),
]


def sanitize_path(url_or_path: str) -> str:
    """
    Sanitiza una ruta o URL eliminando query strings y redactando tokens sensibles.
    """
    if not url_or_path:
        return ''
    parsed = urlsplit(url_or_path)
    path = parsed.path or url_or_path

    for pattern, replacement in SENSITIVE_URL_PATTERNS:
        path = pattern.sub(replacement, path)

    return path


def sanitize_referer(referer: str) -> str:
    """
    Sanitiza el referer eliminando query strings y redactando tokens sensibles.
    """
    if not referer:
        return ''
    parsed = urlsplit(referer)
    sanitized_path = sanitize_path(parsed.path)
    if parsed.scheme and parsed.netloc:
        return urlunsplit((parsed.scheme, parsed.netloc, sanitized_path, '', ''))
    return sanitized_path


def _parse_ip(value):
    """Normaliza una entrada de X-Forwarded-For; devuelve None si no es una IP."""
    if not value:
        return None
    value = value.strip().strip('"')
    if value.startswith('[') and ']' in value:
        value = value[1:value.index(']')]
    elif value.count(':') == 1 and '.' in value:
        value = value.split(':', 1)[0]
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def get_client_ip(request):
    """Devuelve la IP real del cliente validando la cadena X-Forwarded-For.

    nginx es el único proxy de confianza y añade la IP del peer al final de la
    cabecera ($proxy_add_x_forwarded_for), por lo que la IP fiable está a
    TRUSTED_PROXY_COUNT posiciones desde la derecha. Todo lo que el cliente
    inyecte a la izquierda de esa posición se descarta, evitando el spoofing.
    """
    proxy_count = getattr(settings, 'TRUSTED_PROXY_COUNT', 1)
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')

    if forwarded_for and proxy_count > 0:
        chain = [ip for ip in (_parse_ip(part) for part in forwarded_for.split(',')) if ip]
        if len(chain) >= proxy_count:
            return chain[-proxy_count]

    return _parse_ip(request.META.get('REMOTE_ADDR', '')) or ''


def _atomic_incr(cache_key: str, timeout: int = 3600) -> int:
    """
    Incrementa atómicamente un contador en cache.
    Si la clave no existe, la inicializa en 0 con el timeout indicado y la incrementa a 1.
    """
    try:
        return cache.incr(cache_key)
    except ValueError:
        cache.add(cache_key, 0, timeout)
        try:
            return cache.incr(cache_key)
        except ValueError:
            return 1

TENANT_EXEMPT_PREFIXES = (
    '/videos/calendario/suscripcion/',
)

RESERVED_SUBDOMAINS = {'www'}


class TenantMiddleware:
    """
    Resuelve el tenant (Organization) a partir del subdominio del Host header
    y lo pone en request.tenant.

    Modo passthrough (Fase 1): si no hay subdominio reconocido, asigna Sant Josep
    para que ilovevoley.es siga funcionando. En Fase 2 se elimina el passthrough.
    """

    PASSTHROUGH = False
    RESERVED_SUBDOMAINS = RESERVED_SUBDOMAINS

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host_header = request.META.get('HTTP_HOST', '')
        host = host_header.split(':')[0].lower()
        port = host_header.split(':')[1] if ':' in host_header else ''
        parts = host.split('.')
        root_domain = '.'.join(parts[-2:]) if len(parts) >= 2 else host

        if host == root_domain:
            if self.PASSTHROUGH:
                request.tenant = get_organization_by_slug('santjosep')
            else:
                request.tenant = None
        else:
            subdomain = parts[0]
            if subdomain in self.RESERVED_SUBDOMAINS:
                port_suffix = f":{port}" if port and port not in ('80', '443') else ""
                target_url = f"{request.scheme}://{root_domain}{port_suffix}{request.get_full_path()}"
                return redirect(target_url, permanent=True)

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
            sanitized_url = sanitize_path(request.path)
            # Obtener información del error
            error_data = {
                'url': sanitized_url,
                'method': request.method,
                'ip': get_client_ip(request),
                'user_agent': request.META.get('HTTP_USER_AGENT', '')[:200],
                'referer': sanitize_referer(request.META.get('HTTP_REFERER', '')),
                'timestamp': datetime.now().isoformat(),
                'user': str(request.user) if request.user.is_authenticated else 'Anonymous',
            }

            # Contador atómico diario de errores 404
            daily_count_key = f"404_count_{datetime.now().strftime('%Y%m%d')}"
            _atomic_incr(daily_count_key, timeout=60 * 60 * 48)

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

            send_404_immediate_alert(request)

        except Exception as e:
            logger.error(f"Error logging 404: {str(e)}")


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
        daily_count_key = f"404_count_{yesterday.strftime('%Y%m%d')}"
        daily_count = cache.get(daily_count_key)
        total_errors = daily_count if daily_count is not None else len(errors)
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
            
        # Contar errores en la última hora usando incremento atómico
        cache_key = f"404_count_{datetime.now().strftime('%Y%m%d_%H')}"
        current_count = _atomic_incr(cache_key, timeout=60 * 60)
        
        # Si supera el umbral, enviar alerta
        if current_count == threshold:  # Solo enviar una vez por hora
            from ilovevoley.core.tasks import send_404_immediate_alert_task

            send_404_immediate_alert_task.delay(
                current_count,
                datetime.now().strftime('%H:00'),
                sanitize_path(request.path),
                admin_emails,
            )
            logger.warning(f"Alerta 404 encolada: {current_count} errores")
            return True
            
    except Exception as e:
        logger.error(f"Error enviando alerta 404: {str(e)}")
        return False


# CSP relajada para el panel de administración. Unfold/Alpine.js evalúan
# expresiones con `new Function` y las plantillas del admin inyectan bloques
# <script>/<style> sin nonce, por lo que no puede aplicarse la política
# estricta del sitio público. Es una excepción acotada a /admin/ (solo staff).
ADMIN_CSP = {
    'default-src': [CSP.SELF],
    'script-src': [CSP.SELF, CSP.UNSAFE_INLINE, CSP.UNSAFE_EVAL],
    'style-src': [CSP.SELF, CSP.UNSAFE_INLINE],
    'img-src': [CSP.SELF, 'data:', 'blob:'],
    'font-src': [CSP.SELF, 'data:'],
    'frame-src': [CSP.SELF],
    'connect-src': [CSP.SELF],
    'object-src': [CSP.NONE],
    'base-uri': [CSP.SELF],
    'form-action': [CSP.SELF],
    'frame-ancestors': [CSP.NONE],
}


class AdminCSPMiddleware:
    """Aplica una CSP relajada (Unfold/Alpine) a las rutas del admin.

    Se registra justo después de ContentSecurityPolicyMiddleware: al procesar
    la respuesta en orden inverso, este middleware sobrescribe la config antes
    de que el middleware nativo construya la cabecera.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.admin_prefix = '/' + settings.ADMIN_URL.lstrip('/')

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(self.admin_prefix):
            response._csp_config = ADMIN_CSP
            response._csp_ro_config = None
        return response
