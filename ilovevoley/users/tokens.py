"""
Utilidades para generación y verificación de tokens seguros de usuarios (#327).
"""
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

DEACTIVATE_ACCOUNT_SALT = "ilovevoley.users.deactivate_account.v1"
DEACTIVATE_TOKEN_MAX_AGE = 45 * 86400  # 45 días

# Baja voluntaria desde un mail puntual (p. ej. novedades de temporada): no depende
# del ciclo de inactividad; caduca por sí sola.
VOLUNTARY_DEACTIVATE_SALT = "ilovevoley.users.deactivate_account.voluntary.v1"
VOLUNTARY_DEACTIVATE_TOKEN_MAX_AGE = 90 * 86400  # 90 días


def generate_deactivation_token(user):
    """Genera un token firmado con timestamp para permitir la desactivación de cuenta.

    Incluye la marca temporal del aviso para que el token quede invalidado
    automáticamente si el usuario inicia sesión y se resetea su inactividad.
    """
    signer = TimestampSigner(salt=DEACTIVATE_ACCOUNT_SALT)
    ts = int(user.inactivity_warning_sent_at.timestamp()) if user.inactivity_warning_sent_at else 0
    return signer.sign(f"{user.pk}:{ts}")


def generate_voluntary_deactivation_token(user):
    """Token de baja voluntaria para cuentas activas (sin aviso de inactividad)."""
    signer = TimestampSigner(salt=VOLUNTARY_DEACTIVATE_SALT)
    return signer.sign(str(user.pk))


def verify_voluntary_deactivation_token(token, max_age=VOLUNTARY_DEACTIVATE_TOKEN_MAX_AGE):
    """Verifica un token de baja voluntaria. Válido mientras la cuenta exista."""
    if not token:
        return None
    from django.contrib.auth import get_user_model

    signer = TimestampSigner(salt=VOLUNTARY_DEACTIVATE_SALT)
    try:
        user_id = int(signer.unsign(token, max_age=max_age))
    except (BadSignature, SignatureExpired, ValueError):
        return None
    return get_user_model().objects.filter(pk=user_id).first()


def verify_deactivation_token(token, max_age=DEACTIVATE_TOKEN_MAX_AGE):
    """Verifica un token firmado de desactivación (inactividad o baja voluntaria).

    Comprueba la firma, expiración y que la advertencia siga activa en el usuario
    (se invalida automáticamente si el usuario inició sesión entre medias).
    Si no es un token de inactividad, prueba el de baja voluntaria.

    Retorna:
        User: objeto de usuario si es válido.
        None: si no es válido, expiró o fue invalidado por login.
    """
    if not token:
        return None
    from django.contrib.auth import get_user_model
    User = get_user_model()

    signer = TimestampSigner(salt=DEACTIVATE_ACCOUNT_SALT)
    try:
        data = signer.unsign(token, max_age=max_age)
        user_id_str, ts_str = data.split(':', 1)
        user_id = int(user_id_str)
        token_ts = int(ts_str)
    except (BadSignature, SignatureExpired, ValueError):
        return verify_voluntary_deactivation_token(token)

    user = User.objects.filter(pk=user_id).first()
    if not user:
        return None

    # Si el usuario está activo pero ya no tiene avisos activos (p. ej. inició sesión y renovó),
    # el token de este aviso queda invalidado.
    if user.is_active:
        current_ts = int(user.inactivity_warning_sent_at.timestamp()) if user.inactivity_warning_sent_at else 0
        if user.inactivity_warning_level == 0 or token_ts != current_ts:
            return verify_voluntary_deactivation_token(token)

    return user
