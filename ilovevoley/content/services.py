"""Servicios de dominio para el módulo de contenido (vídeos e imágenes)."""
from django.core.exceptions import PermissionDenied

from ilovevoley.core.tenant_utils import can_moderate_images


def moderate_image(actor, tenant, image, decision, notes=''):
    """Modera una imagen aplicando validación estricta de tenant y permisos.

    Args:
        actor: Usuario que ejecuta la moderación.
        tenant: Organization del contexto actual (o None si es superuser global).
        image: Instancia de Image a moderar.
        decision: 'approve', 'reject', True o False.
        notes: Notas u observaciones de la moderación.

    Returns:
        Image: La instancia moderada y guardada.

    Raises:
        PermissionDenied: Si el actor no tiene permisos o si la imagen pertenece a otro tenant.
        ValueError: Si la decisión no es válida o si la imagen ya fue moderada.
    """
    if not actor or not actor.is_authenticated:
        raise PermissionDenied("Se requiere autenticación para moderar.")

    # Validar permisos generales de moderación
    if not can_moderate_images(actor, tenant):
        raise PermissionDenied("No tienes permisos para moderar imágenes en esta organización.")

    # Aislamiento multi-tenant: si hay tenant, la imagen debe pertenecer estrictamente a él
    if tenant is not None:
        if image.organization_id != tenant.id:
            raise PermissionDenied("No puedes moderar una imagen perteneciente a otra organización.")
    else:
        # Sin tenant en el contexto, solo un superusuario puede moderar imágenes
        if not actor.is_superuser:
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
