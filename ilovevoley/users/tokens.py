"""
Utilidades para generación y verificación de tokens seguros de usuarios (#327).
"""
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

DEACTIVATE_ACCOUNT_SALT = "ilovevoley.users.deactivate_account.v1"
DEACTIVATE_TOKEN_MAX_AGE = 45 * 86400  # 45 días


def generate_deactivation_token(user):
    """Genera un token firmado con timestamp para permitir la desactivación de cuenta."""
    signer = TimestampSigner(salt=DEACTIVATE_ACCOUNT_SALT)
    return signer.sign(str(user.pk))


def verify_deactivation_token(token, max_age=DEACTIVATE_TOKEN_MAX_AGE):
    """Verifica un token firmado de desactivación.

    Retorna:
        int: user_id si el token es válido y no ha expirado.
        None: si la firma no es válida o ha caducado.
    """
    if not token:
        return None
    signer = TimestampSigner(salt=DEACTIVATE_ACCOUNT_SALT)
    try:
        user_id_str = signer.unsign(token, max_age=max_age)
        return int(user_id_str)
    except (BadSignature, SignatureExpired, ValueError):
        return None
