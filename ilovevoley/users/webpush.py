import json
import logging
from django.conf import settings
from pywebpush import webpush as pywebpush_send, WebPushException

logger = logging.getLogger(__name__)


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
