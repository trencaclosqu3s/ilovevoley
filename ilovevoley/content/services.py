"""Servicios de dominio para el módulo de contenido (vídeos e imágenes)."""
import logging

from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext as _

from ilovevoley.core.tenant_utils import can_moderate_images

logger = logging.getLogger(__name__)


def moderate_image(actor, tenant, image, decision, notes='', validate_permission=True):
    """Modera una imagen aplicando validación estricta de tenant y permisos.

    Args:
        actor: Usuario que ejecuta la moderación.
        tenant: Organization del contexto actual (o None si es superuser global).
        image: Instancia de Image a moderar.
        decision: 'approve', 'reject', True o False.
        notes: Notas u observaciones de la moderación.
        validate_permission: Si es True, comprueba los permisos del actor contra el tenant.

    Returns:
        Image: La instancia moderada y guardada.

    Raises:
        PermissionDenied: Si el actor no tiene permisos o si la imagen pertenece a otro tenant.
        ValueError: Si la decisión no es válida o si la imagen ya fue moderada.
    """
    if not actor or not actor.is_authenticated:
        raise PermissionDenied(_("Se requiere autenticación para moderar."))

    # Validar permisos generales de moderación
    if validate_permission and not can_moderate_images(actor, tenant):
        raise PermissionDenied(_("No tienes permisos para moderar imágenes en esta organización."))

    # Aislamiento multi-tenant: si hay tenant, la imagen debe pertenecer estrictamente a él
    if tenant is not None:
        if image.organization_id != tenant.id:
            raise PermissionDenied(_("No puedes moderar una imagen perteneciente a otra organización."))
    elif not actor.is_superuser:
        raise PermissionDenied(_("Solo un superusuario puede moderar imágenes a nivel global."))



    # Validar estado de la imagen
    if image.status != 'pending':
        raise ValueError(_("La imagen no está en estado pendiente de moderación."))

    # Validar decisión
    if isinstance(decision, str):
        if decision == 'approve':
            approved = True
        elif decision == 'reject':
            approved = False
        else:
            raise ValueError(_("Decisión de moderación no válida: %(decision)s") % {'decision': decision})
    elif isinstance(decision, bool):
        approved = decision
    else:
        raise ValueError(_("Decisión de moderación no válida: %(decision)s") % {'decision': decision})

    # Delegar en el método del modelo para actualizar campos y persistir
    image.moderate(moderator=actor, approved=approved, notes=notes)

    # Avisar del contenido del partido solo cuando ya es visible: en la subida aún
    # estaba pendiente y `match_detail` no lo mostraba (#286). Un fallo de caché no
    # debe tumbar la moderación, que ya está persistida.
    if approved and image.match_id and image.organization_id:
        try:
            queue_match_media_push(
                match_id=image.match_id,
                media_type='photo',
                organization_id=image.organization_id,
            )
        except Exception as exc:
            logger.exception("No se pudo encolar el aviso de media del partido: %s", exc)

    return image


def match_media_push_cache_keys(organization_id: int, match_id: int) -> dict:
    """Claves de caché del debounce de media de partido.

    Compartidas entre el encolado (`queue_match_media_push`) y la tarea que
    consolida el aviso: si divergen, la tarea lee una clave que nadie escribió.
    """
    return {
        'pending': f"match_media_push_pending:{organization_id}:{match_id}",
        'scheduled': f"match_media_push_scheduled:{organization_id}:{match_id}",
        'cooldown': f"match_media_push_cooldown:{organization_id}:{match_id}",
    }


def queue_match_media_push(match_id: int, media_type: str, organization_id: int) -> bool:
    """Encola aviso push agrupado por debounce para fotos o vídeos de un partido.

    - Agrupa múltiples subidas de fotos y/o vídeos para el mismo partido dentro de una ventana de tiempo.
    - Programa una tarea con countdown (o respeta cooldown) para emitir un único push consolidado.
    - notification_type: 'match_media'.
    """
    from django.conf import settings
    from django.core.cache import cache
    from django.db import transaction

    debounce_seconds = settings.MATCH_MEDIA_PUSH_DEBOUNCE_SECONDS
    keys = match_media_push_cache_keys(organization_id, match_id)
    pending_key = keys['pending']
    scheduled_key = keys['scheduled']
    cooldown_key = keys['cooldown']

    # Si estamos en cooldown activo tras un envío reciente, no encolar nuevo aviso
    if cache.get(cooldown_key):
        return False

    # Actualizar medios pendientes
    pending = cache.get(pending_key) or {'photos': False, 'videos': False}
    if media_type == 'photo':
        pending['photos'] = True
    elif media_type == 'video':
        pending['videos'] = True
    cache.set(pending_key, pending, timeout=debounce_seconds * 4)

    # Programar la tarea si no está ya programada para esta ventana
    if cache.add(scheduled_key, True, timeout=debounce_seconds * 2):
        from ilovevoley.content.tasks import notify_match_media_push_task

        def _schedule():
            notify_match_media_push_task.apply_async(
                args=[organization_id, match_id],
                countdown=debounce_seconds,
            )

        transaction.on_commit(_schedule, robust=True)
        return True

    return False

