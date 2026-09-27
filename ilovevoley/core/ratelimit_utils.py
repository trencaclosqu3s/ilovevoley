"""
Utilidades para rate limiting y extracción de IP del cliente.
"""


def get_client_ip(request):
    """
    Extrae la IP real del cliente considerando cabeceras de proxy inverso (Nginx).
    Prioriza X-Forwarded-For (primera IP de la lista), luego X-Real-IP,
    y finalmente REMOTE_ADDR.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
        if ip:
            return ip

    x_real_ip = request.META.get('HTTP_X_REAL_IP')
    if x_real_ip:
        ip = x_real_ip.strip()
        if ip:
            return ip

    return request.META.get('REMOTE_ADDR', '127.0.0.1')


def ratelimit_post_login_key(group, request):
    """
    Clave para limitar intentos de login por identificador introducido (usuario o email).
    Permite mitigar ataques distribuidos de fuerza bruta hacia un usuario específico.
    """
    val = request.POST.get('login', '').strip().lower()
    return f"login:{val}"


def ratelimit_post_email_key(group, request):
    """
    Clave para limitar solicitudes de recuperación de contraseña por email destino.
    """
    val = request.POST.get('email', '').strip().lower()
    return f"email:{val}"
