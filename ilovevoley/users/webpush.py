import json
import logging
from urllib.parse import urlparse

from django.conf import settings
from py_vapid import Vapid
from pywebpush import webpush as pywebpush_send, WebPushException

logger = logging.getLogger(__name__)

# Hosts de los servicios push de los navegadores soportados. La suscripción es un
# endpoint anónimo, así que sin lista blanca el worker haría POST a cualquier URL
# (SSRF ciego hacia la red interna). Ver #286.
_PUSH_ENDPOINT_HOSTS = {
    'fcm.googleapis.com',
    'updates.push.services.mozilla.com',
    'web.push.apple.com',
}
_PUSH_ENDPOINT_HOST_SUFFIXES = (
    '.push.apple.com',
    '.notify.windows.com',
)

MAX_PUSH_ENDPOINT_LENGTH = 500

# Timeout por petición: el broadcast es secuencial y `pywebpush` no pone límite
# por defecto, de modo que un endpoint que no responde bloquearía el worker.
PUSH_REQUEST_TIMEOUT_SECONDS = 10


def is_valid_push_endpoint(url: str) -> bool:
    """Valida que el endpoint sea HTTPS y apunte a un servicio push conocido."""
    if not url or len(url) > MAX_PUSH_ENDPOINT_LENGTH:
        return False
    parsed = urlparse(url)
    if parsed.scheme != 'https':
        return False
    host = (parsed.hostname or '').lower()
    if not host:
        return False
    if host in _PUSH_ENDPOINT_HOSTS:
        return True
    return host.endswith(_PUSH_ENDPOINT_HOST_SUFFIXES)


def send_web_push(subscription, payload, ttl=86400):
    """
    Send a Web Push notification to a specific device subscription.
    If endpoint returns 404 or 410 (Gone/Revoked), delete the expired subscription.
    """
    private_key = getattr(settings, 'VAPID_PRIVATE_KEY', '')
    claims_sub = getattr(settings, 'VAPID_CLAIMS_SUB', 'mailto:admin@ilovevoley.es')

    if not private_key:
        logger.warning('send_web_push: VAPID_PRIVATE_KEY not configured')
        return False

    # Suscripciones anteriores a la validación de endpoint: no se envían a ciegas.
    if not is_valid_push_endpoint(subscription.endpoint):
        logger.warning('send_web_push: endpoint no permitido, se omite el envío')
        return False

    # pywebpush interpreta un str como base64 DER o ruta a fichero, no como texto PEM.
    if private_key.lstrip().startswith('-----BEGIN'):
        private_key = Vapid.from_pem(private_key.encode())

    subscription_info = {
        'endpoint': subscription.endpoint,
        'keys': {
            'p256dh': subscription.p256dh,
            'auth': subscription.auth,
        },
    }

    vapid_claims = {
        'sub': claims_sub,
    }

    try:
        pywebpush_send(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=private_key,
            vapid_claims=vapid_claims,
            ttl=ttl,
            timeout=PUSH_REQUEST_TIMEOUT_SECONDS,
        )
        return True
    except WebPushException as ex:
        status_code = getattr(getattr(ex, 'response', None), 'status_code', None)
        if status_code in (404, 410):
            # Endpoint revoked or expired by push service: automatic cleanup
            subscription.delete()
        else:
            logger.warning('send_web_push: error dispatching push (status %s): %s', status_code, ex)
        return False
    except Exception as ex:
        logger.warning('send_web_push: unexpected error dispatching push: %s', ex)
        return False
