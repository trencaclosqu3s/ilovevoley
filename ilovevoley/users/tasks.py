from celery import shared_task
from django.db.models import Q
from .models import CategoryPreference, WebPushSubscription
from .webpush import send_web_push


@shared_task(name='notify_web_push_subscription')
def notify_web_push_subscription_task(subscription_id, payload):
    """Dispatch a push notification to a specific subscription."""
    try:
        sub = WebPushSubscription.objects.get(pk=subscription_id)
    except WebPushSubscription.DoesNotExist:
        return False
    return send_web_push(sub, payload)


@shared_task(name='notify_web_push_user')
def notify_web_push_user_task(user_id, title, body, url=None, badge_count=None, organization_id=None):
    """Dispatch a push notification to all registered devices of a user."""
    qs = WebPushSubscription.objects.filter(user_id=user_id)
    if organization_id:
        qs = qs.filter(organization_id=organization_id)

    payload = {
        'title': title,
        'body': body,
        'url': url or '/',
        'badge_count': badge_count,
    }

    dispatched = 0
    for sub in qs:
        if send_web_push(sub, payload):
            dispatched += 1
    return dispatched


@shared_task(name='notify_web_push_organization')
def notify_web_push_organization_task(organization_id, title, body, url=None, badge_count=None, category_ids=None):
    """Broadcast a push notification to the devices of an organization.

    Con ``category_ids`` solo reciben el aviso quienes tienen alguna de esas categorías entre sus
    preferencias; quien no ha elegido ninguna (o es anónimo) recibe todo, igual que en la web.
    """
    subs = WebPushSubscription.objects.filter(organization_id=organization_id)
    if category_ids:
        prefs = CategoryPreference.objects.filter(organization_id=organization_id)
        interested = prefs.filter(categories__in=category_ids).values('user_id')
        with_prefs = prefs.filter(categories__isnull=False).values('user_id')
        subs = subs.filter(Q(user_id__in=interested) | ~Q(user_id__in=with_prefs))
    payload = {
        'title': title,
        'body': body,
        'url': url or '/',
        'badge_count': badge_count,
    }

    dispatched = 0
    for sub in subs:
        if send_web_push(sub, payload):
            dispatched += 1
    return dispatched
