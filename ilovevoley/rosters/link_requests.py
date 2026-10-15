"""Self-service de vínculo cuenta ↔ ficha (#531).

El usuario no puede escribir el vínculo directamente: toda alta pasa por una
solicitud que resuelve un moderador del club. La identificación de la ficha
reutiliza la verificación estricta de ``person_adopt`` (nombre, apellidos y año
exactos) y exige que la ficha sea visible en el club del usuario, para no
convertir el formulario en un buscador de personas de otros clubes.

Las reglas de negocio viven aquí, no en la vista: una ficha solo puede
pertenecer a un usuario (``kind=self``) y aprobar es lo único que escribe el
vínculo.
"""
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ilovevoley.core.tenant_utils import person_belongs_to_tenant
from .models import Person, PersonLinkRequest

# Anti-abuso: cuántas solicitudes sin resolver puede acumular una cuenta.
MAX_PENDING_REQUESTS = 5


def find_person(first_name, last_name, birth_year):
    """Ficha global con identidad exacta, o ``None``.

    Usa ``_base_manager`` porque la identidad de ``Person`` es global: la
    visibilidad por club se comprueba aparte.
    """
    if not (first_name and last_name and birth_year):
        return None
    try:
        year = int(birth_year)
    except (TypeError, ValueError):
        return None
    return Person._base_manager.filter(
        first_name=first_name, last_name=last_name, birth_year=year,
    ).first()


def has_own_person(user):
    """¿La cuenta ya tiene una ficha propia vinculada?

    El vínculo es global (no por club), así que se consulta con el manager base.
    """
    return Person._base_manager.filter(user=user).exists()


def validate_link_request(user, person, kind):
    """Motivo por el que no se puede crear la solicitud, o ``None``."""
    if kind == PersonLinkRequest.Kind.SELF:
        if has_own_person(user):
            return _('Ya tienes una ficha vinculada a tu cuenta.')
        if person.user_id == user.id:
            return _('Esa ficha ya está vinculada a tu cuenta.')
        if person.user_id is not None:
            return _('Esa ficha ya está vinculada a otra cuenta.')
    elif kind == PersonLinkRequest.Kind.CHILD:
        if person.user_id == user.id:
            return _('No puedes vincular tu propia ficha como hijo/a.')
        if user.children.filter(pk=person.pk).exists():
            return _('Esa ficha ya está vinculada como tu hijo/a.')
    else:
        return _('Tipo de vínculo no válido.')
    return None


def create_link_request(user, organization, first_name, last_name, birth_year, kind):
    """Crea (o reutiliza) la solicitud pendiente.

    Devuelve ``(solicitud, error)``. En éxito ``error`` es ``None``. Es
    idempotente: si ya existe una solicitud pendiente para esa (usuario, ficha)
    la devuelve sin duplicar ni revalidar.
    """
    person = find_person(first_name, last_name, birth_year)
    if person is None or not person_belongs_to_tenant(person, organization):
        # Mismo mensaje en ambos casos: no se confirma la existencia de fichas
        # de otros clubes.
        return None, _('No encontramos ninguna ficha con esos datos en tu club.')

    error = validate_link_request(user, person, kind)
    if error:
        return None, error

    pending_count = PersonLinkRequest.objects.filter(
        user=user, organization=organization, status=PersonLinkRequest.Status.PENDING,
    ).count()
    existing = PersonLinkRequest.objects.filter(
        user=user, person=person, status=PersonLinkRequest.Status.PENDING,
    ).first()
    if existing is not None:
        return existing, None
    if pending_count >= MAX_PENDING_REQUESTS:
        return None, _('Has enviado demasiadas solicitudes. Espera a que se resuelvan.')

    try:
        with transaction.atomic():
            return PersonLinkRequest.objects.create(
                user=user, person=person, organization=organization, kind=kind,
            ), None
    except IntegrityError:
        # Carrera con otra petición idéntica: la restricción deja una sola pendiente.
        return PersonLinkRequest.objects.filter(
            user=user, person=person, status=PersonLinkRequest.Status.PENDING,
        ).first(), None


def approve_link_request(link_request, moderator):
    """Escribe el vínculo y marca la solicitud como aprobada.

    Devuelve un mensaje de error legible o ``None``. Si la ficha ya pertenece a
    ``kind=self`` (otra cuenta o un usuario con ficha), no se toca nada y la
    solicitud sigue pendiente para que el moderador la rechace.
    """
    if link_request.status != PersonLinkRequest.Status.PENDING:
        return _('Esta solicitud ya está resuelta.')

    user = link_request.user
    person = Person._base_manager.get(pk=link_request.person_id)

    with transaction.atomic():
        if link_request.kind == PersonLinkRequest.Kind.SELF:
            if person.user_id is None:
                if Person._base_manager.filter(user=user).exclude(pk=person.pk).exists():
                    return _('La cuenta ya tiene otra ficha vinculada.')
                person.user = user
                person.save(update_fields=['user'])
            elif person.user_id != user.id:
                return _('Esa ficha ya está vinculada a otra cuenta.')
        elif link_request.kind == PersonLinkRequest.Kind.CHILD:
            user.children.add(person)
        else:
            return _('Tipo de vínculo no válido.')

        link_request.status = PersonLinkRequest.Status.APPROVED
        link_request.resolved_at = timezone.now()
        link_request.resolved_by = moderator
        link_request.save(update_fields=['status', 'resolved_at', 'resolved_by'])
    return None


def reject_link_request(link_request, moderator):
    """Marca la solicitud como rechazada. Devuelve error o ``None``."""
    if link_request.status != PersonLinkRequest.Status.PENDING:
        return _('Esta solicitud ya está resuelta.')
    link_request.status = PersonLinkRequest.Status.REJECTED
    link_request.resolved_at = timezone.now()
    link_request.resolved_by = moderator
    link_request.save(update_fields=['status', 'resolved_at', 'resolved_by'])
    return None
