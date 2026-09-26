"""Celery tasks for async email notifications (issue #114)."""
import logging
import os

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model

from ilovevoley.core.email_utils import get_moderation_recipients, send_notification_email

logger = logging.getLogger(__name__)
User = get_user_model()


@shared_task(name='notify_image_pending')
def notify_image_pending_task(image_id):
    """Send pending-image moderation email for a single Image."""
    from ilovevoley.content.models import Image
    from ilovevoley.core.moderation_views import generate_moderation_token

    if not settings.EMAIL_NOTIFICATIONS.get('image_pending', True):
        return False

    try:
        image = Image.objects.select_related('uploaded_by', 'match__league').get(pk=image_id)
    except Image.DoesNotExist:
        logger.warning('notify_image_pending: image %s gone', image_id)
        return False

    if image.status != 'pending':
        return False

    approve_token = generate_moderation_token('image', image.id, 'approve')
    reject_token = generate_moderation_token('image', image.id, 'reject')

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

    context = {
        'image': image,
        'user': image.uploaded_by,
        'site_name': 'I Love Voley',
        'admin_url': f'/admin/videos/image/{image.id}/change/',
        'image_cid': 'pending_image' if embedded_images else None,
        'approve_url': f'/moderate/image/{approve_token}/',
        'reject_url': f'/moderate/image/{reject_token}/',
    }
    return send_notification_email(
        subject=f'Nueva imagen pendiente de moderación: {image.title}',
        template_name='emails/image_pending.html',
        context=context,
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
        .select_related('uploaded_by')
        .order_by('id')
    )
    if not images:
        return False

    uploader = images[0].uploaded_by
    context = {
        'images': images,
        'count': len(images),
        'user': uploader,
        'site_name': 'I Love Voley',
        'moderation_url': '/core/moderacion/',
    }
    return send_notification_email(
        subject=f'{len(images)} nuevas imágenes pendientes de moderación',
        template_name='emails/images_pending_batch.html',
        context=context,
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
        subject=f'Nuevo usuario pendiente de aprobación: {user.username}',
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

    if membership.is_approved or not membership.user.is_approved:
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
        subject=f'Nueva membresía pendiente: {user.username} en {organization.name}',
        template_name='emails/new_membership_pending.html',
        context=context,
        recipient_list=get_moderation_recipients(organization),
    )
