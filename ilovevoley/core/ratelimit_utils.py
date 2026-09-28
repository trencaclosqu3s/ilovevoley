"""
Utilidades para rate limiting y extracción de IP del cliente.
"""
import hashlib

from django.conf import settings
from django.core.cache import cache

from ilovevoley.core.middleware import get_client_ip  # noqa: F401  (re-export)


def ratelimit_post_login_key(group, request):
    """
    Clave para limitar intentos de login por IP + identificador introducido.

    Combinar IP y credencial evita que un atacante bloquee globalmente la cuenta
    de una víctima repartiendo intentos desde muchas IPs (DoS de cuenta). Los
    formularios vacíos se discriminan por IP para no compartir un único cubo
    entre todos los envíos vacíos del sistema.
    """
    val = request.POST.get('login', '').strip().lower()
    ip = get_client_ip(request)
    if val:
        return f"login:{ip}:{val}"
    return f"login-empty:{ip}"


def ratelimit_post_email_key(group, request):
    """
    Clave para limitar solicitudes de recuperación de contraseña por IP + email destino.
    """
    val = request.POST.get('email', '').strip().lower()
    ip = get_client_ip(request)
    if val:
        return f"email:{ip}:{val}"
    return f"email-empty:{ip}"


def normalize_credential(value):
    """Normaliza la credencial/email para usarlo como clave canónica de identidad."""
    return (value or '').strip().lower()


def credential_fingerprint(value):
    """Hash truncado de la credencial para logs/alertas sin exponer PII."""
    return hashlib.sha256((value or '').encode('utf-8')).hexdigest()[:12]


def _global_key(scope, value):
    return f"auth-global:{scope}:{value}"


def record_global_failure(scope, value, window=None):
    """
    Incrementa el contador global de una credencial/email y devuelve el total.

    Complemento al límite per-IP + credencial de PR #200 (#202): acota la fuerza
    bruta distribuida contra una misma identidad desde muchas IPs, donde cada IP
    agota solo su propio cubo. El contador tiene TTL corto y se usa únicamente
    para contar fallos de login o solicitudes de reset; nunca logins correctos.
    """
    if window is None:
        window = settings.AUTH_GLOBAL_FAILURE_WINDOW_SECONDS
    key = _global_key(scope, value)
    if cache.add(key, 1, window):
        return 1
    try:
        return cache.incr(key)
    except ValueError:
        # La clave expiró entre el add y el incr (o el backend no la auto-crea
        # en incr): se reinician valor y ventana. La carrera es benigna y, como
        # mucho, alarga la ventana unos segundos.
        cache.set(key, 1, window)
        return 1


def reset_global_failures(scope, value):
    """Limpia el contador global tras un login correcto de esa credencial."""
    cache.delete(_global_key(scope, value))
