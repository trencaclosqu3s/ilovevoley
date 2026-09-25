"""Entrega autorizada de medios privados.

Nginx no sirve directamente ``/media/images/`` ni ``/media/people/``: reenvía
esas peticiones a Django, que resuelve el tenant del subdominio, comprueba la
propiedad/estado del recurso y delega la entrega del archivo a nginx mediante
``X-Accel-Redirect`` (zona interna ``/protected-media/``). Los recursos no
sensibles (logos de organizaciones y avatares) siguen sirviéndose estáticos.
"""
import mimetypes
import os
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, HttpResponse

from .tenant_utils import (
    tenant_access_required,
    user_is_tenant_staff,
)

PUBLIC_PREFIXES = ('organizations/', 'avatars/')


def _use_x_accel():
    return getattr(settings, 'PROTECTED_MEDIA_USE_X_ACCEL', not settings.DEBUG)


def _normalize(path):
    """Normaliza la ruta y rechaza traversal o rutas absolutas."""
    if not path or path.startswith('/') or '\\' in path:
        raise Http404
    normalized = os.path.normpath(path).replace(os.sep, '/')
    if normalized.startswith('..'):
        raise Http404
    return normalized


def _image_is_allowed(image, user, tenant):
    if user.is_superuser:
        return True
    # Imágenes sin organización (datos heredados) se consideran compartidas.
    if image.organization_id is not None and image.organization_id != tenant.pk:
        raise Http404
    if image.status == 'approved':
        return True
    if user_is_tenant_staff(user, tenant):
        return True
    return image.uploaded_by_id == user.pk


def _person_is_allowed(person, user, tenant):
    if user.is_superuser:
        return True
    club_id = tenant.club_id
    if club_id is None:
        # Tenant sin club federado: solo se permiten fichas sin roles, que no
        # revelan afiliación a ningún club concreto.
        return not (person.player_roles.exists() or person.staff_roles.exists())
    has_roles = person.player_roles.exists() or person.staff_roles.exists()
    if not has_roles:
        return True
    return person.player_roles.filter(
        is_active=True, team__club_id=club_id
    ).exists() or person.staff_roles.filter(
        is_active=True, team__club_id=club_id
    ).exists()


def _authorize(path, user, tenant):
    from ilovevoley.content.models import Image
    from ilovevoley.rosters.models import Person

    if path.startswith('images/'):
        image = Image.objects.filter(image=path).only('status', 'organization', 'uploaded_by').first()
        if image is None:
            raise Http404
        if not _image_is_allowed(image, user, tenant):
            raise PermissionDenied
        return
    if path.startswith('people/'):
        person = Person.objects.filter(photo=path).first()
        if person is None:
            raise Http404
        if not _person_is_allowed(person, user, tenant):
            raise Http404
        return
    raise Http404


def _serve(path):
    content_type = mimetypes.guess_type(path)[0] or 'application/octet-stream'
    if _use_x_accel():
        response = HttpResponse(content_type=content_type)
        prefix = getattr(settings, 'PROTECTED_MEDIA_INTERNAL_URL', '/protected-media/')
        response['X-Accel-Redirect'] = f'{prefix}{quote(path, safe="/")}'
    else:
        base = Path(settings.MEDIA_ROOT).resolve()
        full = (base / path).resolve()
        if base not in full.parents:
            raise Http404
        if not full.is_file():
            raise Http404
        response = FileResponse(full.open('rb'), content_type=content_type)
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Security-Policy'] = "default-src 'none'; img-src 'self'; sandbox"
    response['Content-Disposition'] = 'inline'
    return response


@tenant_access_required(api=True)
def _serve_protected(request, path):
    _authorize(path, request.user, getattr(request, 'tenant', None))
    return _serve(path)


def protected_media(request, path):
    normalized = _normalize(path)
    if normalized.startswith(PUBLIC_PREFIXES):
        # En producción nginx ya sirve estos prefijos estáticamente; si la
        # petición llega a Django es porque no existe la location (dev) y se
        # sirven directamente sin requerir autenticación.
        if _use_x_accel():
            raise Http404
        return _serve(normalized)
    return _serve_protected(request, normalized)
