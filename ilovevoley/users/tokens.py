"""
Utilidades para generación y verificación de tokens seguros de usuarios (#327).
"""
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

DEACTIVATE_ACCOUNT_SALT = "ilovevoley.users.deactivate_account.v1"
DEACTIVATE_TOKEN_MAX_AGE = 45 * 86400  # 45 días


def generate_deactivation_token(user):
    """Genera un token firmado con timestamp para permitir la desactivación de cuenta.

    Incluye la marca temporal del aviso para que el token quede invalidado
    automáticamente si el usuario inicia sesión y se resetea su inactividad.
    """
    signer = TimestampSigner(salt=DEACTIVATE_ACCOUNT_SALT)
    ts = int(user.inactivity_warning_sent_at.timestamp()) if user.inactivity_warning_sent_at else 0
    return signer.sign(f"{user.pk}:{ts}")


def verify_deactivation_token(token, max_age=DEACTIVATE_TOKEN_MAX_AGE):
    """Verifica un token firmado de desactivación.

    Comprueba la firma, expiración y que la advertencia siga activa en el usuario
    (se invalida automáticamente si el usuario inició sesión entre medias).

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
        return None

    user = User.objects.filter(pk=user_id).first()
    if not user:
        return None

    # Si el usuario está activo pero ya no tiene avisos activos (p. ej. inició sesión y renovó),
    # el token de este aviso queda invalidado.
    if user.is_active:
        current_ts = int(user.inactivity_warning_sent_at.timestamp()) if user.inactivity_warning_sent_at else 0
        if user.inactivity_warning_level == 0 or token_ts != current_ts:
            return None

    return user
