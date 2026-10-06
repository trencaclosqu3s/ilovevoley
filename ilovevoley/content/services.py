"""Servicios de dominio para el módulo de contenido (vídeos e imágenes)."""
import logging
from collections import defaultdict

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.utils.translation import gettext as _

from ilovevoley.core.tenant_utils import can_moderate_images, can_tag_image

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

    # El etiquetado de una foto aún pendiente no avisó; al aprobarla ya es visible,
    # así que se avisa ahora al deportista y a su familia (#362).
    if approved and image.organization_id:
        person_ids = list(image.persons.values_list('id', flat=True))
        if person_ids:
            from ilovevoley.content.tasks import notify_image_tagged_push_task
            from ilovevoley.core.email_utils import enqueue_on_commit

            for person_id in person_ids:
                enqueue_on_commit(
                    notify_image_tagged_push_task,
                    image.organization_id, person_id, [image.id], actor.id,
                )

    return image


def delete_image_with_files(image):
    """Elimina una imagen y sus ficheros (original y miniaturas) de forma definitiva."""
    for field_name in (
        'image',
        'thumbnail_small',
        'thumbnail_large',
        'thumbnail_small_avif',
        'thumbnail_large_avif',
    ):
        field = getattr(image, field_name, None)
        if field:
            field.delete(save=False)
    image.delete()


def taggable_persons(match, tenant):
    """Fichas activas del club ofrecidas para etiquetar deportistas.

    Con partido se limita a los jugadores de sus dos equipos; sin partido se
    ofrecen todas las fichas activas del club. En ambos casos el queryset queda
    acotado al club del tenant (aislamiento multi-tenant).
    """
    from ilovevoley.rosters.models import Person, PlayerRole

    base = Person.objects.for_tenant(tenant).filter(is_active=True)
    if match is None:
        return base.order_by('last_name', 'first_name')

    team_ids = [tid for tid in (match.home_team_id, match.away_team_id) if tid]
    roster_ids = PlayerRole.objects.filter(
        team_id__in=team_ids, is_active=True
    ).values_list('person_id', flat=True)
    return base.filter(Q(pk__in=roster_ids)).order_by('last_name', 'first_name')


def tagging_push_audience(person, actor=None):
    """Usuarios a los que interesa que se etiquete a ``person`` en una foto.

    Devuelve ``(player_id, parent_ids)``: el propio deportista (usuario vinculado
    a la ficha) y los familiares que lo tienen como hijo. Se excluye a quien
    realizó el etiquetado para no avisarle de su propia acción.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()
    actor_id = getattr(actor, 'id', None)
    player_id = person.user_id
    if player_id == actor_id:
        player_id = None
    parent_ids = set(
        User.objects.filter(children=person).values_list('id', flat=True)
    )
    parent_ids.discard(actor_id)
    parent_ids.discard(person.user_id)
    return player_id, parent_ids


def apply_image_tags(actor, tenant, images, persons, *, replace=False, validate_permission=True):
    """Etiqueta personas en imágenes respetando aislamiento y permisos.

    Con ``replace`` sustituye las etiquetas de cada imagen; sin él añade las
    nuevas sin quitar las existentes. Las imágenes que el actor no puede
    etiquetar (o de otro club) se omiten. Devuelve el número de imágenes
    modificadas. Por cada ficha etiquetada de nuevo se avisa al deportista y a
    su familia.
    """
    # TODO(#122): descartar fichas sin consentimiento de imagen cuando exista el
    # campo en Person; hoy todas las fichas del club son etiquetables.
    persons = list(persons)
    changed = 0
    added_by_person = defaultdict(set)
    org_by_person = {}
    for image in images:
        if validate_permission and not can_tag_image(actor, tenant, image):
            continue
        if tenant is not None and image.organization_id != tenant.id and not actor.is_superuser:
            continue
        existing = set(image.persons.values_list('id', flat=True))
        if replace:
            image.persons.set(persons)
        else:
            image.persons.add(*persons)
        for person in persons:
            # Solo se avisa de fotos visibles; en una pendiente el aviso se
            # pospone a la aprobación (#286, #362).
            if person.id not in existing and image.status == 'approved':
                added_by_person[person.id].add(image.id)
                org_by_person.setdefault(person.id, image.organization_id)
        changed += 1

    if added_by_person:
        from ilovevoley.content.tasks import notify_image_tagged_push_task
        from ilovevoley.core.email_utils import enqueue_on_commit

        actor_id = getattr(actor, 'id', None)
        for person_id, image_ids in added_by_person.items():
            org_id = org_by_person.get(person_id)
            if org_id is None:
                continue
            enqueue_on_commit(notify_image_tagged_push_task, org_id, person_id, list(image_ids), actor_id)
    return changed


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

