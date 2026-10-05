"""Celery tasks for async email notifications (issue #114)."""
import logging
import os

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import translation
from django.utils.translation import gettext as _

from ilovevoley.core.i18n import group_emails_by_language
from ilovevoley.core.email_utils import get_moderation_recipients, send_notification_email

logger = logging.getLogger(__name__)
User = get_user_model()


@shared_task(name='notify_image_pending')
def notify_image_pending_task(image_id):
    """Send pending-image moderation email for a single Image."""
    from django.urls import reverse

    from ilovevoley.content.models import Image
    from ilovevoley.core.moderation_views import generate_moderation_token
    from ilovevoley.core.tenant_utils import build_absolute_url

    if not settings.EMAIL_NOTIFICATIONS.get('image_pending', True):
        return False

    try:
        image = Image.objects.select_related(
            'uploaded_by', 'organization', 'match__league'
        ).get(pk=image_id)
    except Image.DoesNotExist:
        logger.warning('notify_image_pending: image %s gone', image_id)
        return False

    if image.status != 'pending':
        return False

    tenant = image.organization
    approve_token = generate_moderation_token(
        'image', image.id, 'approve', tenant_id=image.organization_id
    )
    reject_token = generate_moderation_token(
        'image', image.id, 'reject', tenant_id=image.organization_id
    )

    embedded_images = {}
    attachments = []
    if image.image:
        try:
            image_path = image.image.path
            if os.path.exists(image_path):
                embedded_images['pending_image'] = image_path
                attachments.append(image_path)
        except Exception:
            logger.warning('notify_image_pending: could not read file for image %s', image_id)

    approve_path = reverse('moderate_image', kwargs={'token': approve_token})
    reject_path = reverse('moderate_image', kwargs={'token': reject_token})
    admin_rel_path = f"/{settings.ADMIN_URL.rstrip('/')}/content/image/{image.id}/change/"

    context = {
        'image': image,
        'user': image.uploaded_by,
        'site_name': tenant.name if tenant else 'I Love Voley',
        'admin_url': build_absolute_url(admin_rel_path),
        'image_cid': 'pending_image' if embedded_images else None,
        'approve_url': build_absolute_url(approve_path, tenant=tenant),
        'reject_url': build_absolute_url(reject_path, tenant=tenant),
    }
    return send_notification_email(
        subject=lambda: _('Nueva imagen pendiente de moderación: %(title)s') % {'title': image.title},
        template_name='emails/image_pending.html',
        context=context,
        recipient_list=get_moderation_recipients(tenant),
        attachments=attachments or None,
        embedded_images=embedded_images or None,
    )


@shared_task(name='notify_images_pending_batch')
def notify_images_pending_batch_task(image_ids):
    """Single summary email for a bulk upload of pending images."""
    from ilovevoley.content.models import Image

    if not settings.EMAIL_NOTIFICATIONS.get('image_pending', True):
        return False

    images = list(
        Image.objects.filter(id__in=image_ids, status='pending')
        .select_related('uploaded_by', 'organization')
        .order_by('id')
    )
    if not images:
        return False

    uploader = images[0].uploaded_by
    tenant = images[0].organization
    from django.urls import reverse

    from ilovevoley.core.tenant_utils import build_absolute_url

    context = {
        'images': images,
        'count': len(images),
        'user': uploader,
        'site_name': tenant.name if tenant else 'I Love Voley',
        'moderation_url': build_absolute_url(
            reverse('core:moderation_panel'), tenant=tenant
        ),
    }
    return send_notification_email(
        subject=lambda: _('%(count)s nuevas imágenes pendientes de moderación') % {'count': len(images)},
        template_name='emails/images_pending_batch.html',
        context=context,
        recipient_list=get_moderation_recipients(tenant),
    )


@shared_task(name='notify_new_user_pending')
def notify_new_user_pending_task(user_id, tenant_id, moderation_url, is_oauth=False):
    from ilovevoley.core.models import Organization

    if not settings.EMAIL_NOTIFICATIONS.get('new_user_pending', True):
        return False

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return False

    tenant = None
    if tenant_id is not None:
        try:
            tenant = Organization.objects.get(pk=tenant_id)
        except Organization.DoesNotExist:
            tenant = None

    context = {
        'user': user,
        'site_name': 'I Love Voley',
        'tenant': tenant,
        'is_oauth': is_oauth,
        'moderation_url': moderation_url,
    }
    return send_notification_email(
        subject=lambda: _('Nuevo usuario pendiente de aprobación: %(username)s') % {'username': user.username},
        template_name='emails/new_user_pending.html',
        context=context,
        recipient_list=get_moderation_recipients(tenant),
    )


@shared_task(name='notify_membership_pending')
def notify_membership_pending_task(membership_id):
    from django.urls import reverse

    from ilovevoley.core.tenant_utils import build_tenant_url
    from ilovevoley.users.models import Membership

    if not settings.EMAIL_NOTIFICATIONS.get('new_user_pending', True):
        return False

    try:
        membership = Membership.objects.select_related('user', 'organization').get(
            pk=membership_id
        )
    except Membership.DoesNotExist:
        return False

    if membership.is_approved:
        return False

    organization = membership.organization
    user = membership.user
    context = {
        'user': user,
        'tenant': organization,
        'membership': membership,
        'site_name': 'I Love Voley',
        'moderation_url': (
            f'{build_tenant_url(organization.slug)}'
            f'{reverse("core:moderation_panel").lstrip("/")}'
        ),
    }
    return send_notification_email(
        subject=lambda: _('Nueva membresía pendiente: %(username)s en %(organization)s') % {
            'username': user.username, 'organization': organization.name},
        template_name='emails/new_membership_pending.html',
        context=context,
        recipient_list=get_moderation_recipients(organization),
    )


@shared_task(name='notify_reactivation_pending')
def notify_reactivation_pending_task(user_id, tenant_id=None):
    """Avisa a los moderadores de que una cuenta desactivada pidió reactivarse (#327)."""
    from django.urls import reverse

    from ilovevoley.core.models import Organization
    from ilovevoley.core.tenant_utils import build_tenant_url

    if not settings.EMAIL_NOTIFICATIONS.get('new_user_pending', True):
        return False

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return False

    tenant = Organization.objects.filter(pk=tenant_id).first() if tenant_id is not None else None

    moderation_path = reverse('core:moderation_panel')
    moderation_url = f'{build_tenant_url(tenant.slug)}{moderation_path}' if tenant else moderation_path

    context = {
        'user': user,
        'tenant': tenant,
        'site_name': 'I Love Voley',
        'moderation_url': moderation_url,
        'requested_at': user.reactivation_requested_at,
    }
    return send_notification_email(
        subject=lambda: _('Solicitud de reactivación: %(username)s') % {'username': user.username},
        template_name='emails/reactivation_pending.html',
        context=context,
        recipient_list=get_moderation_recipients(tenant),
    )


@shared_task(name='send_admin_email_to_users')
def send_admin_email_to_users_task(
    subject, message_body, recipient_ids, admin_user_id=None, send_copy=False
):
    from ilovevoley.core.email_utils import send_admin_email_to_users

    recipients = User.objects.filter(pk__in=recipient_ids)
    admin_user = None
    if admin_user_id is not None:
        try:
            admin_user = User.objects.get(pk=admin_user_id)
        except User.DoesNotExist:
            admin_user = None
    return send_admin_email_to_users(
        subject=subject,
        message_body=message_body,
        recipients=recipients,
        admin_user=admin_user,
        send_copy=send_copy,
    )


@shared_task(name='send_404_immediate_alert')
def send_404_immediate_alert_task(count, hour, last_url, recipient_list):
    from django.core.mail import send_mail
    from django.template.loader import render_to_string
    from django.utils.html import strip_tags

    context = {
        'count': count,
        'hour': hour,
        'site_name': 'I Love Voley',
        'last_url': last_url,
    }
    for lang, emails in group_emails_by_language(recipient_list).items():
        with translation.override(lang):
            html_message = render_to_string('emails/404_alert.html', context)
            send_mail(
                subject=_('Alerta: %(count)s errores 404 en la última hora') % {'count': count},
                message=strip_tags(html_message),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=emails,
                html_message=html_message,
                fail_silently=False,
            )
    return True


@shared_task(name='notify_user_moderation_result')
def notify_user_moderation_result_task(user_id, approved, site_url=None, site_name=None):
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return False
    if not user.email:
        return False

    resolved_site_name = site_name or 'I Love Voley'
    if approved:
        return send_notification_email(
            subject=lambda: _('Tu cuenta ha sido aprobada en I Love Voley'),
            template_name='emails/user_approved.html',
            context={
                'user': user,
                'site_name': resolved_site_name,
                'site_url': site_url or '/',
            },
            recipient_list=[user.email],
        )
    return send_notification_email(
        subject=lambda: _('Actualización de tu solicitud en I Love Voley'),
        template_name='emails/user_rejected.html',
        context={'user': user, 'site_name': resolved_site_name},
        recipient_list=[user.email],
    )


@shared_task(name='notify_image_moderation_result')
def notify_image_moderation_result_task(image_id, approved, site_name=None):
    from ilovevoley.content.models import Image

    try:
        image = Image.objects.select_related('uploaded_by').get(pk=image_id)
    except Image.DoesNotExist:
        return False
    if not image.uploaded_by.email:
        return False

    return send_notification_email(
        subject=lambda: _('Tu imagen "%(title)s" ha sido %(status)s') % {
            'title': image.title,
            'status': _('aprobada') if approved else _('rechazada'),
        },
        template_name=(
            'emails/image_approved.html' if approved else 'emails/image_rejected.html'
        ),
        context={
            'image': image,
            'user': image.uploaded_by,
            'site_name': site_name or 'I Love Voley',
            'is_approved': approved,
            'moderation_notes': image.moderation_notes,
        },
        recipient_list=[image.uploaded_by.email],
    )
