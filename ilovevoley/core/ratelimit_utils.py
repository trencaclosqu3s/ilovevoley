"""
Utilidades para rate limiting y extracción de IP del cliente.
"""
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
