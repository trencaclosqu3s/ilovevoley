from celery import shared_task
from django.db.models import Q
from ilovevoley.core.i18n import language_for
from ilovevoley.core.models import Organization
from ilovevoley.core.tenant_utils import build_absolute_url
from .models import CategoryPreference, NotificationPreference, WebPushSubscription
from .webpush import send_web_push


@shared_task(name='notify_web_push_organization')
def notify_web_push_organization_task(
    organization_id, title, body, url=None, badge_count=None, category_ids=None, notification_type=None,
    translations=None,
):
    """Broadcast a push notification to the devices of an organization.

    Con ``category_ids`` solo reciben el aviso quienes tienen alguna de esas categorías entre sus
    preferencias; quien no ha elegido ninguna (o es anónimo) recibe todo, igual que en la web.
    Con ``notification_type`` se excluyen los usuarios que hayan desactivado expresamente ese tipo
    de aviso para esta organización (por defecto todos los tipos están activos; los dispositivos
    anónimos reciben todo).
    ``translations`` (``{lang: {'title', 'body'}}``) permite enviar a cada dispositivo el texto en
    el idioma de su usuario; sin traducción para ese idioma, o con dispositivo anónimo, se usan
    ``title`` y ``body``.
    """
    # Un dispositivo queda ligado a una sola organización (endpoint único), así que un
    # usuario miembro de varios clubes solo recibiría los del club donde se suscribió.
    subs = WebPushSubscription.objects.filter(
        Q(organization_id=organization_id)
        | Q(user__memberships__organization_id=organization_id, user__memberships__is_approved=True)
    ).distinct()
    if category_ids:
        prefs = CategoryPreference.objects.filter(organization_id=organization_id)
        interested = prefs.filter(categories__in=category_ids).values('user_id')
        with_prefs = prefs.filter(categories__isnull=False).values('user_id')
        subs = subs.filter(Q(user_id__in=interested) | ~Q(user_id__in=with_prefs))

    if notification_type:
        disabled_users = NotificationPreference.objects.filter(
            organization_id=organization_id,
            notification_type=str(notification_type),
            is_enabled=False,
        ).values('user_id')
        subs = subs.exclude(user_id__in=disabled_users)

    # El aviso abre el dominio del club emisor, no el donde se suscribió el dispositivo.
    target_url = url or '/'
    org = Organization.objects.filter(pk=organization_id).first()
    if org and target_url.startswith('/'):
        target_url = build_absolute_url(target_url, tenant=org)

    dispatched = 0
    for sub in subs.select_related('user'):
        text = (translations or {}).get(language_for(sub.user)) or {'title': title, 'body': body}
        payload = {
            'title': text['title'],
            'body': text['body'],
            'url': target_url,
            'badge_count': badge_count,
        }
        if send_web_push(sub, payload):
            dispatched += 1
    return dispatched
