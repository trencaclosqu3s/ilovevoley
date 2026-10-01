"""Servicios de dominio para el módulo de contenido (vídeos e imágenes)."""
from django.core.exceptions import PermissionDenied

from ilovevoley.core.tenant_utils import can_moderate_images


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
        raise PermissionDenied("Se requiere autenticación para moderar.")

    # Validar permisos generales de moderación
    if validate_permission and not can_moderate_images(actor, tenant):
        raise PermissionDenied("No tienes permisos para moderar imágenes en esta organización.")

    # Aislamiento multi-tenant: si hay tenant, la imagen debe pertenecer estrictamente a él
    if tenant is not None:
        if image.organization_id != tenant.id:
            raise PermissionDenied("No puedes moderar una imagen perteneciente a otra organización.")
    elif not actor.is_superuser:
        raise PermissionDenied("Solo un superusuario puede moderar imágenes a nivel global.")



    # Validar estado de la imagen
    if image.status != 'pending':
        raise ValueError("La imagen no está en estado pendiente de moderación.")

    # Validar decisión
    if isinstance(decision, str):
        if decision == 'approve':
            approved = True
        elif decision == 'reject':
            approved = False
        else:
            raise ValueError(f"Decisión de moderación no válida: {decision}")
    elif isinstance(decision, bool):
        approved = decision
    else:
        raise ValueError(f"Decisión de moderación no válida: {decision}")

    # Delegar en el método del modelo para actualizar campos y persistir
    image.moderate(moderator=actor, approved=approved, notes=notes)
    return image


def queue_match_media_push(match_id: int, media_type: str, organization_id: int) -> bool:
    """Encola aviso push agrupado por debounce para fotos o vídeos de un partido.

    - Agrupa múltiples subidas de fotos y/o vídeos para el mismo partido dentro de una ventana de tiempo.
    - Programa una tarea con countdown (o respeta cooldown) para emitir un único push consolidado.
    - notification_type: 'match_media'.
    """
    from django.conf import settings
    from django.core.cache import cache
    from django.db import transaction

    debounce_seconds = getattr(settings, 'MATCH_MEDIA_PUSH_DEBOUNCE_SECONDS', 60)
    pending_key = f"match_media_push_pending:{organization_id}:{match_id}"
    scheduled_key = f"match_media_push_scheduled:{organization_id}:{match_id}"
    cooldown_key = f"match_media_push_cooldown:{organization_id}:{match_id}"

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

