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
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse

from .tenant_utils import (
    can_moderate_images,
    tenant_access_required,
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
    if can_moderate_images(user, tenant):
        return True
    return image.uploaded_by_id == user.pk


def _person_is_allowed(person, user, tenant):
    if user.is_superuser:
        return True
    # Ficha global: visible en el club vinculado o donde tenga roles.
    return type(person).objects.for_tenant(tenant).filter(pk=person.pk).exists()


def _authorize(path, user, tenant):
    from ilovevoley.content.models import Image
    from ilovevoley.rosters.models import Person

    if path.startswith('images/'):
        # Las miniaturas viven junto al original (…_400.webp) y se guardan en
        # thumbnail_*; hay que autorizarlas por esos campos, no solo por image=.
        image = Image.objects.filter(
            Q(image=path)
            | Q(thumbnail_small=path)
            | Q(thumbnail_large=path)
            | Q(thumbnail_small_avif=path)
            | Q(thumbnail_large_avif=path)
        ).only('status', 'organization', 'uploaded_by').first()
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


def serve_protected_file(path):
    """API pública para servir un fichero privado ya autorizado.

    Normaliza la ruta y delega en la entrega (``X-Accel-Redirect`` en producción,
    ``FileResponse`` en desarrollo). La autorización es responsabilidad de quien
    llama: esta función solo entrega el fichero indicado.
    """
    return _serve(_normalize(path))


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
