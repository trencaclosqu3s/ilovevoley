"""Tareas Celery de la app content (Vision + miniaturas)."""
import logging

from celery import shared_task
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _

from ilovevoley.content.models import Image
from ilovevoley.core.i18n import push_message
from ilovevoley.content.thumbnails import generate_image_thumbnails
from ilovevoley.videos.utils import (
    check_image_with_vision_api,
    process_vision_tags_for_volleyball,
)

logger = logging.getLogger(__name__)


@shared_task(name='analyze_image_with_vision')
def analyze_image_with_vision_task(image_id, notify_if_pending=True):
    """
    Run Google Vision on a saved Image and optionally notify if still pending.

    Auto-approve uses a conditional UPDATE so a concurrent human moderation
    decision is never overwritten after the Vision API round-trip.
    """
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

    vision_ok = True
    try:
        vision_result = check_image_with_vision_api(
            image.image, extract_labels=True, extract_text=True
        )
        vision_safe = vision_result.get('safe', False)
        auto_tags = image.auto_tags or []
        detected_labels = vision_result.get('labels', [])
        detected_text = vision_result.get('text', '')
        if detected_labels or detected_text:
            auto_tags = process_vision_tags_for_volleyball(
                detected_labels, detected_text
            )

        vision_fields = {
            'vision_api_checked': True,
            'vision_api_safe': vision_safe,
            'vision_api_details': vision_result,
            'auto_tags': auto_tags,
        }

        should_auto_approve = (
            vision_safe
            and vision_result.get('details', {}).get('api_response_ok', False)
            and getattr(settings, 'AUTO_MODERATION_ENABLED', False)
        )

        if should_auto_approve:
            # Only approve if still pending — preserves concurrent human decisions.
            updated = Image.objects.filter(pk=image.pk, status='pending').update(
                **vision_fields,
                status='approved',
                moderated_by=image.uploaded_by,
                moderation_date=timezone.now(),
                moderation_notes=_('Auto-aprobada por Google Vision API'),
            )
            if not updated:
                Image.objects.filter(pk=image.pk).update(**vision_fields)
            elif image.match_id and image.organization_id:
                # La imagen pasa a visible ahora: se avisa del contenido del partido.
                # Un fallo de caché no debe alterar el resultado de la moderación.
                try:
                    from ilovevoley.content.services import queue_match_media_push
                    queue_match_media_push(
                        match_id=image.match_id,
                        media_type='photo',
                        organization_id=image.organization_id,
                    )
                except Exception as exc:
                    logger.exception('No se pudo encolar el aviso de media del partido: %s', exc)
        else:
            Image.objects.filter(pk=image.pk).update(**vision_fields)
    except Exception as e:
        vision_ok = False
        logger.error(
            'Vision API error for image %s: %s', image_id, e, exc_info=True
        )
        Image.objects.filter(pk=image.pk).update(
            vision_api_checked=False,
            vision_api_safe=False,
            vision_api_details={
                'error': str(e),
                'api_response_ok': False,
                'error_type': type(e).__name__,
            },
        )

        if not settings.DEBUG and settings.NOTIFICATION_EMAIL_ENABLED:
            try:
                send_notification_email(
                    subject=lambda: _('Error en Google Vision API'),
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
    return vision_ok


@shared_task(name='generate_image_thumbnails_task')
def generate_image_thumbnails_task(image_id):
    """Genera las miniaturas responsivas de una imagen por su id.

    El nombre es explícito porque las filas de PeriodicTask dependen de él.
    """
    try:
        image = Image.objects.get(pk=image_id)
    except Image.DoesNotExist:
        logger.warning('Imagen %s no encontrada para generar miniaturas', image_id)
        return {'generated': 0}

    try:
        return {'generated': len(generate_image_thumbnails(image))}
    except Exception:
        # Un original corrupto o un fallo de storage debe quedar trazado y marcar
        # la tarea como fallida (Sentry/monitorización), no pasar en silencio.
        logger.exception('Fallo generando miniaturas de la imagen %s', image_id)
        raise


@shared_task(name='build_album_zip')
def build_album_zip_task(job_id, organization_id, scope, scope_id):
    """Comprime imágenes aprobadas de un partido o álbum en un ZIP temporal.

    El nombre es explícito porque las filas de PeriodicTask dependen de él.
    """
    from ilovevoley.content.album_zip import (
        REL_DIR,
        build_album_zip_file,
        cleanup_expired_album_zips,
        get_job_state,
        job_dest_path,
        mark_job_failed,
        mark_job_ready,
    )

    cleanup_expired_album_zips()

    state = get_job_state(job_id)
    if not state:
        logger.warning('build_album_zip: job %s missing from cache', job_id)
        return {'ok': False, 'reason': 'missing_job'}

    qs = Image.objects.filter(organization_id=organization_id, status='approved')
    if scope == 'match':
        qs = qs.filter(match_id=int(scope_id))
    elif scope == 'album_group':
        qs = qs.filter(album_group_id=scope_id)
    else:
        mark_job_failed(job_id, f'unknown scope {scope}')
        return {'ok': False, 'reason': 'bad_scope'}

    dest = job_dest_path(job_id)
    filename = state.get('filename') or f'album-{job_id}.zip'
    try:
        count = build_album_zip_file(queryset=qs, dest_path=dest)
        if count == 0:
            if dest.exists():
                dest.unlink(missing_ok=True)
            mark_job_failed(job_id, 'empty')
            return {'ok': False, 'reason': 'empty'}
        rel_path = f'{REL_DIR}/{job_id}.zip'
        mark_job_ready(job_id, organization_id, rel_path, filename)
        return {'ok': True, 'count': count, 'path': rel_path}
    except Exception as exc:
        if dest.exists():
            dest.unlink(missing_ok=True)
        mark_job_failed(job_id, exc)
        raise


@shared_task(name='cleanup_expired_album_zips')
def cleanup_expired_album_zips_task():
    """Elimina ZIPs temporales caducados bajo MEDIA_ROOT/tmp/album_zips/.

    El nombre es explícito porque las filas de PeriodicTask dependen de él.
    """
    from ilovevoley.content.album_zip import cleanup_expired_album_zips

    removed = cleanup_expired_album_zips()
    return {'removed': removed}


@shared_task(name='notify_match_media_push')
def notify_match_media_push_task(organization_id, match_id):
    """Envía la notificación push consolidada tras la ventana de debounce para fotos/vídeos de un partido."""
    from django.conf import settings
    from django.core.cache import cache
    from django.urls import reverse

    from ilovevoley.competitions.models import Match
    from ilovevoley.competitions.services.notifications import match_category_ids
    from ilovevoley.content.services import match_media_push_cache_keys
    from ilovevoley.core.models import Organization
    from ilovevoley.users.tasks import notify_web_push_organization_task

    debounce_seconds = settings.MATCH_MEDIA_PUSH_DEBOUNCE_SECONDS
    keys = match_media_push_cache_keys(organization_id, match_id)
    pending_key = keys['pending']
    scheduled_key = keys['scheduled']
    cooldown_key = keys['cooldown']

    pending = cache.get(pending_key)
    cache.delete(pending_key)
    cache.delete(scheduled_key)

    if not pending or not (pending.get('photos') or pending.get('videos')):
        return False

    # Activar cooldown para evitar re-notificaciones inmediatas ante ráfagas tardías
    cache.set(cooldown_key, True, timeout=debounce_seconds)

    try:
        match = Match.all_objects.select_related('home_team', 'away_team', 'league').get(pk=match_id)
        org = Organization.objects.get(pk=organization_id, is_active=True)
    except (Match.DoesNotExist, Organization.DoesNotExist):
        return False

    has_photos = pending.get('photos', False)
    has_video_media = pending.get('videos', False)

    home_name = match.home_team_display
    away_name = match.away_team_display
    match_display = f"{home_name} - {away_name}"
    teams_vs = f"{home_name} vs {away_name}"

    if not (has_photos or has_video_media):
        return False

    def build():
        if has_photos and has_video_media:
            return (
                _('Fotos y vídeos: %(teams)s') % {'teams': teams_vs},
                _('Se han subido fotos y vídeos del partido %(match)s') % {'match': match_display},
            )
        if has_photos:
            return (
                _('Fotos: %(teams)s') % {'teams': teams_vs},
                _('Se han subido fotos del partido %(match)s') % {'match': match_display},
            )
        return (
            _('Vídeos: %(teams)s') % {'teams': teams_vs},
            _('Se han subido vídeos del partido %(match)s') % {'match': match_display},
        )

    category_ids = match_category_ids(match)
    url = reverse('competitions:match_detail', args=[match.id])

    notify_web_push_organization_task.delay(
        organization_id=org.id,
        **push_message(build),
        url=url,
        category_ids=category_ids,
        notification_type='match_media',
        match_id=match_id,
    )
    return True

