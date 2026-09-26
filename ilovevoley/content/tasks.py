"""Celery tasks for content moderation (Google Vision, issue #114)."""
import logging

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from ilovevoley.videos.utils import (
    check_image_with_vision_api,
    process_vision_tags_for_volleyball,
)

logger = logging.getLogger(__name__)


@shared_task(name='analyze_image_with_vision')
def analyze_image_with_vision_task(image_id, notify_if_pending=True):
    """
    Run Google Vision on a saved Image and optionally notify if still pending.
    """
    from ilovevoley.content.models import Image
    from ilovevoley.core.email_utils import send_notification_email
    from ilovevoley.core.tasks import notify_image_pending_task

    try:
        image = Image.objects.select_related('uploaded_by').get(pk=image_id)
    except Image.DoesNotExist:
        logger.warning('analyze_image_with_vision: image %s gone', image_id)
        return False

    if not getattr(settings, 'GOOGLE_VISION_ENABLED', False):
        if notify_if_pending and image.status == 'pending':
            notify_image_pending_task(image_id)
        return False

    try:
        vision_result = check_image_with_vision_api(
            image.image, extract_labels=True, extract_text=True
        )
        image.vision_api_checked = True
        image.vision_api_safe = vision_result.get('safe', False)
        image.vision_api_details = vision_result

        detected_labels = vision_result.get('labels', [])
        detected_text = vision_result.get('text', '')
        if detected_labels or detected_text:
            image.auto_tags = process_vision_tags_for_volleyball(
                detected_labels, detected_text
            )

        if (
            vision_result.get('safe', False)
            and vision_result.get('details', {}).get('api_response_ok', False)
            and getattr(settings, 'AUTO_MODERATION_ENABLED', False)
            and image.status == 'pending'
        ):
            image.status = 'approved'
            image.moderated_by = image.uploaded_by
            image.moderation_date = timezone.now()
            image.moderation_notes = 'Auto-aprobada por Google Vision API'

        image.save()
    except Exception as e:
        logger.error(
            'Vision API error for image %s: %s', image_id, e, exc_info=True
        )
        image.vision_api_checked = False
        image.vision_api_safe = False
        image.vision_api_details = {
            'error': str(e),
            'api_response_ok': False,
            'error_type': type(e).__name__,
        }
        image.save(update_fields=[
            'vision_api_checked', 'vision_api_safe', 'vision_api_details',
        ])

        if not settings.DEBUG and settings.NOTIFICATION_EMAIL_ENABLED:
            try:
                send_notification_email(
                    subject='Error en Google Vision API',
                    template_name='emails/vision_api_error.html',
                    context={
                        'error': str(e),
                        'user': image.uploaded_by,
                        'image_title': image.title,
                    },
                    recipient_list=getattr(settings, 'ADMIN_EMAIL_LIST', None),
                )
            except Exception as email_error:
                logger.error('Failed to notify Vision API error: %s', email_error)

    image.refresh_from_db()
    if notify_if_pending and image.status == 'pending':
        notify_image_pending_task(image_id)
    return True
