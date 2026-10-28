import logging
from datetime import timedelta
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from ilovevoley.core.i18n import language_for
from ilovevoley.core.models import Organization
from ilovevoley.core.tenant_utils import build_absolute_url
from .models import (
    CategoryPreference, NotificationPreference, WebPushAudit, WebPushSubscription,
)
from .privacy import build_export_zip
from .webpush import send_web_push

logger = logging.getLogger(__name__)


@shared_task(name='notify_web_push_organization')
def notify_web_push_organization_task(
    organization_id, title, body, url=None, badge_count=None, category_ids=None, notification_type=None,
    translations=None, match_id=None, user_ids=None,
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
    Con ``user_ids`` el aviso se limita a los dispositivos de esos usuarios (p. ej. el etiquetado
    en fotos, que solo interesa al deportista y a su familia).
    """
    # Un dispositivo queda ligado a una sola organización (endpoint único), así que un
    # usuario miembro de varios clubes solo recibiría los del club donde se suscribió.
    subs = WebPushSubscription.objects.filter(
        Q(organization_id=organization_id)
        | Q(user__memberships__organization_id=organization_id, user__memberships__is_approved=True)
    ).distinct()
    if user_ids is not None:
        subs = subs.filter(user_id__in=list(user_ids))
    prefs = CategoryPreference.objects.filter(organization_id=organization_id)
    by_category = Q()
    if category_ids:
        interested = prefs.filter(categories__in=category_ids).values('user_id')
        with_prefs = prefs.filter(categories__isnull=False).values('user_id')
        by_category = Q(user_id__in=interested) | ~Q(user_id__in=with_prefs)
    if match_id:
        # Aviso de partido: quien sigue equipos en el club solo lo recibe si juega uno de
        # ellos (sus categorías no cuentan); el resto sigue con el filtro por categoría.
        from ilovevoley.competitions.models import Match
        team_ids = Match.all_objects.filter(pk=match_id).values_list('home_team_id', 'away_team_id').first() or ()
        following = prefs.filter(teams__in=[t for t in team_ids if t]).values('user_id')
        team_followers = prefs.filter(teams__isnull=False).values('user_id')
        subs = subs.filter(Q(user_id__in=following) | (~Q(user_id__in=team_followers) & by_category))
    elif category_ids:
        subs = subs.filter(by_category)

    if notification_type:
        disabled_users = NotificationPreference.objects.filter(
            organization_id=organization_id,
            notification_type=str(notification_type),
            is_enabled=False,
        ).values('user_id')
        subs = subs.exclude(user_id__in=disabled_users)

    candidates = list(subs.select_related('user'))
    candidate_count = len(candidates)

    # El aviso abre el dominio del club emisor, no el donde se suscribió el dispositivo.
    target_url = url or '/'
    if target_url.startswith('/'):
        org = Organization.objects.filter(pk=organization_id).first()
        if org:
            target_url = build_absolute_url(target_url, tenant=org)

    dispatched = 0
    failed = 0
    for sub in candidates:
        text = (translations or {}).get(language_for(sub.user)) or {'title': title, 'body': body}
        payload = {
            'title': text['title'],
            'body': text['body'],
            'url': target_url,
            'badge_count': badge_count,
        }
        if send_web_push(sub, payload):
            dispatched += 1
        else:
            failed += 1

    try:
        with transaction.atomic():
            WebPushAudit.objects.create(
                organization_id=organization_id,
                notification_type=str(notification_type) if notification_type else '',
                match_id=match_id,
                candidates_count=candidate_count,
                dispatched_count=dispatched,
                failed_count=failed,
            )
    except Exception as exc:
        logger.warning(
            'notify_web_push_organization_task: error al registrar auditoría (org=%s): %s',
            organization_id, exc, exc_info=True,
        )
    return dispatched


@shared_task(name='cleanup_expired_web_push_audits')
def cleanup_expired_web_push_audits_task(days=90):
    """Elimina registros de auditoría de avisos push con más de ``days`` días de antigüedad."""

    cutoff = timezone.now() - timedelta(days=days)
    deleted, _ = WebPushAudit.objects.filter(created_at__lt=cutoff).delete()
    return {'deleted': deleted}


def _get_user_primary_tenant(user):
    """Obtiene la organización principal del usuario a través de sus membresías aprobadas."""
    membership = user.memberships.filter(is_approved=True).select_related('organization').first()
    return membership.organization if membership else None


def _send_inactivity_warning_email(user, warning_level, days_remaining, deadline_date, site_name=None):
    """Envía el email de aviso de inactividad en el idioma del usuario (#327)."""
    from django.urls import reverse
    from django.utils.translation import gettext as _
    from ilovevoley.core.email_utils import send_notification_email
    from .tokens import generate_deactivation_token

    if not settings.EMAIL_NOTIFICATIONS.get('user_inactivity_warning', False):
        return False

    tenant = _get_user_primary_tenant(user)
    login_url = build_absolute_url(reverse('account_login'), tenant=tenant)
    token = generate_deactivation_token(user)
    deactivation_url = build_absolute_url(reverse('deactivate_account', args=[token]), tenant=tenant)

    resolved_site_name = site_name or (tenant.name if tenant else getattr(settings, 'SITE_NAME', 'I Love Voley'))

    if warning_level == 2:
        subject = lambda: _('Último aviso: Tu cuenta en %(site_name)s se desactivará en %(days)d días') % {
            'site_name': resolved_site_name,
            'days': days_remaining,
        }
    else:
        subject = lambda: _('Aviso de inactividad: Tu cuenta en %(site_name)s se desactivará en %(days)d días') % {
            'site_name': resolved_site_name,
            'days': days_remaining,
        }

    return send_notification_email(
        subject=subject,
        template_name='emails/user_inactivity_warning.html',
        context={
            'user': user,
            'warning_level': warning_level,
            'days_remaining': days_remaining,
            'deadline_date': deadline_date,
            'login_url': login_url,
            'deactivation_url': deactivation_url,
            'site_name': resolved_site_name,
        },
        recipient_list=[user.email],
    )


@shared_task(name='process_inactive_users')
def process_inactive_users_task(first_warning_days=335, final_warning_days=358, deactivation_days=365):
    """Procesa el ciclo de vida y la retención de usuarios inactivos (#327).

    - Primer aviso a los ``first_warning_days`` días (~11 meses / 30 días de margen).
    - Segundo aviso urgente a los ``final_warning_days`` días (~11 meses y 23 días / 7 días de margen).
    - Desactivación a los ``deactivation_days`` días (~12 meses / is_active=False).
    """
    from django.contrib.auth import get_user_model
    from django.db.models.functions import Coalesce

    User = get_user_model()
    now = timezone.now()

    cutoff_first = now - timedelta(days=first_warning_days)
    cutoff_final = now - timedelta(days=final_warning_days)
    cutoff_deact = now - timedelta(days=deactivation_days)

    candidates = (
        User.objects.filter(
            is_active=True,
            is_approved=True,
            is_staff=False,
            is_superuser=False,
        )
        .exclude(email='')
        .exclude(email__isnull=True)
        .annotate(effective_activity=Coalesce('last_login', 'date_joined'))
        .filter(effective_activity__lte=cutoff_first)
    )

    first_warnings_sent = 0
    final_warnings_sent = 0
    deactivated_count = 0

    for user in candidates.iterator():
        effective = user.effective_activity

        # 1. Desactivación (inactividad >= 365 días y plazos de gracia del aviso cumplidos)
        if effective <= cutoff_deact:
            can_deactivate = False
            if user.inactivity_warning_level == 2 and user.inactivity_warning_sent_at:
                can_deactivate = now >= user.inactivity_warning_sent_at + timedelta(days=7)
            elif user.inactivity_warning_level == 1 and user.inactivity_warning_sent_at:
                can_deactivate = now >= user.inactivity_warning_sent_at + timedelta(days=30)

            if can_deactivate:
                user.is_active = False
                user.save(update_fields=['is_active'])
                user.web_push_subscriptions.all().delete()
                deactivated_count += 1
                continue

        # 2. Segundo aviso urgente (inactividad >= 358 días, nivel 1 previo y al menos 15 días entre avisos)
        if effective <= cutoff_final:
            if user.inactivity_warning_level == 1:
                min_interval = (user.inactivity_warning_sent_at or effective) + timedelta(days=15)
                if now >= min_interval:
                    days_remaining = 7
                    deadline = now + timedelta(days=days_remaining)
                    if _send_inactivity_warning_email(user, warning_level=2, days_remaining=days_remaining, deadline_date=deadline):
                        user.inactivity_warning_level = 2
                        user.inactivity_warning_sent_at = now
                        user.save(update_fields=['inactivity_warning_level', 'inactivity_warning_sent_at'])
                        final_warnings_sent += 1
                        continue

        # 3. Primer aviso (inactividad >= 335 días y aún sin avisos)
        if effective <= cutoff_first:
            if user.inactivity_warning_level == 0:
                days_remaining = 30
                deadline = now + timedelta(days=days_remaining)
                if _send_inactivity_warning_email(user, warning_level=1, days_remaining=days_remaining, deadline_date=deadline):
                    user.inactivity_warning_level = 1
                    user.inactivity_warning_sent_at = now
                    user.save(update_fields=['inactivity_warning_level', 'inactivity_warning_sent_at'])
                    first_warnings_sent += 1

    return {
        'first_warnings_sent': first_warnings_sent,
        'final_warnings_sent': final_warnings_sent,
        'deactivated_count': deactivated_count,
    }


@shared_task(name='build_data_export')
def build_data_export_task(export_id, organization_id=None):
    from django.core.files.base import ContentFile
    from django.urls import reverse
    from django.utils.translation import gettext as _
    from ilovevoley.core.email_utils import send_notification_email
    from .models import DataExport, PrivacyAuditEvent
    from .privacy import (
        generate_export_token,
        is_erased,
    )

    try:
        export = DataExport.objects.select_related('user').get(
            pk=export_id, status=DataExport.Status.PENDING,
        )
    except DataExport.DoesNotExist:
        return

    user = export.user
    if is_erased(user):
        return

    try:
        payload = build_export_zip(user)

        try:
            export.refresh_from_db()
            user.refresh_from_db()
        except (DataExport.DoesNotExist, user.__class__.DoesNotExist):
            return

        if is_erased(user) or export.status != DataExport.Status.PENDING:
            return

        now = timezone.now()
        filename = f'{user.pk}_{now.strftime("%Y%m%d%H%M%S")}.zip'
        export.file.save(filename, ContentFile(payload), save=False)
        export.status = DataExport.Status.READY
        export.expires_at = now + timedelta(days=7)
        export.save(update_fields=['file', 'status', 'expires_at'])

        club_count = user.memberships.count()
        PrivacyAuditEvent.objects.create(
            user_id=None,
            action=PrivacyAuditEvent.Action.EXPORT,
            club_count=club_count,
        )

        token = generate_export_token(export)
        path = reverse('download_data_export', args=[token])
        org = Organization.objects.filter(pk=organization_id).first() if organization_id else None
        if org is None:
            first_membership = (
                user.memberships.filter(is_approved=True)
                .select_related('organization')
                .first()
            )
            if first_membership:
                org = first_membership.organization
        download_url = build_absolute_url(path, tenant=org)

        if user.email:
            send_notification_email(
                subject=lambda: _('Tus datos están listos'),
                template_name='emails/data_export_ready.html',
                context={'download_url': download_url, 'user': user},
                recipient_list=[user.email],
            )
    except Exception:
        logger.error('Error generating data export %s', export_id, exc_info=True)
        if export.file:
            export.file.delete(save=False)
            export.file = ''
        export.status = DataExport.Status.FAILED
        export.save(update_fields=['file', 'status'])
        if not is_erased(user) and user.email:
            send_notification_email(
                subject=lambda: _('Error al generar la exportación de tus datos'),
                template_name='emails/data_export_failed.html',
                context={'user': user},
                recipient_list=[user.email],
            )


@shared_task(name='cleanup_expired_data_exports')
def cleanup_expired_data_exports_task():
    from .privacy import cleanup_expired_data_exports

    cleanup_expired_data_exports()


@shared_task(name='cleanup_expired_privacy_audit_events')
def cleanup_expired_privacy_audit_events_task():
    from .privacy import cleanup_expired_privacy_audit_events

    cleanup_expired_privacy_audit_events()


