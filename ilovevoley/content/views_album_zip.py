"""Vistas HTTP para solicitud, estado y descarga de ZIP de álbum (#127)."""
from urllib.parse import quote

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.utils.text import get_valid_filename
from django.views.decorators.http import require_GET, require_POST

from ilovevoley.competitions.models import Match
from ilovevoley.content.album_zip import (
    create_pending_job,
    get_job_state,
    parse_download_token,
    safe_resolve_media_path,
)
from ilovevoley.content.models import Image
from ilovevoley.content.tasks import build_album_zip_task
from ilovevoley.core.tenancy import get_tenant_object_or_404
from ilovevoley.core.tenant_utils import tenant_access_required


def _use_x_accel():
    return getattr(settings, 'PROTECTED_MEDIA_USE_X_ACCEL', not settings.DEBUG)


def _approved_match_qs(tenant, match):
    return Image.objects.for_tenant(tenant).filter(match=match, status='approved')


def _approved_album_qs(tenant, album_group_id):
    return Image.objects.for_tenant(tenant).filter(
        album_group_id=album_group_id, status='approved',
    )


def _enqueue(request, *, scope, scope_id, filename, queryset):
    if not queryset.exists():
        return JsonResponse({'error': 'No hay imágenes aprobadas para descargar.'}, status=400)
    job_id = create_pending_job(
        organization_id=request.tenant.pk,
        user_id=request.user.pk,
        scope=scope,
        scope_id=scope_id,
        filename=filename,
    )
    build_album_zip_task.delay(job_id, request.tenant.pk, scope, str(scope_id))
    return JsonResponse({'job_id': job_id, 'status': 'pending'})


@tenant_access_required(api=True)
@require_POST
def request_match_album_zip(request, match_id):
    match = get_tenant_object_or_404(
        Match.objects.select_related('home_team', 'away_team', 'league'),
        request.tenant, user=request.user, id=match_id,
    )
    qs = _approved_match_qs(request.tenant, match)
    home = getattr(match.home_team, 'name', None) or 'local'
    away = getattr(match.away_team, 'name', None) or 'visitante'
    filename = get_valid_filename(f'partido-{match.id}-{home}-vs-{away}.zip')
    return _enqueue(
        request, scope='match', scope_id=match.id, filename=filename, queryset=qs,
    )


@tenant_access_required(api=True)
@require_POST
def request_album_group_zip(request, album_group_id):
    qs = _approved_album_qs(request.tenant, album_group_id)
    if not qs.exists():
        raise Http404('Álbum no encontrado')
    album_name = qs.first().album_name or 'album'
    safe_name = get_valid_filename(album_name) or str(album_group_id)
    filename = get_valid_filename(f'album-{safe_name}.zip')
    return _enqueue(
        request,
        scope='album_group',
        scope_id=album_group_id,
        filename=filename,
        queryset=qs,
    )


@tenant_access_required(api=True)
@require_GET
def album_zip_status(request, job_id):
    state = get_job_state(str(job_id))
    if not state or state.get('organization_id') != request.tenant.pk:
        raise Http404
    if state.get('user_id') != request.user.pk and not request.user.is_superuser:
        raise Http404
    payload = {'status': state.get('status', 'pending'), 'job_id': str(job_id)}
    if state.get('status') == 'ready':
        payload['download_url'] = state.get('download_url')
        payload['filename'] = state.get('filename')
    if state.get('status') == 'failed':
        payload['error'] = state.get('error') or 'No se pudo generar el ZIP.'
    return JsonResponse(payload)


@tenant_access_required(api=True)
@require_GET
def album_zip_download(request):
    token = request.GET.get('token')
    if not token:
        raise Http404
    parsed = parse_download_token(token)
    if parsed is None:
        raise Http404
    job_id, organization_id, rel_path, filename = parsed
    if organization_id != request.tenant.pk:
        raise Http404
    state = get_job_state(job_id)
    if state is not None and state.get('organization_id') != request.tenant.pk:
        raise Http404
    try:
        full = safe_resolve_media_path(rel_path)
    except ValueError:
        raise Http404 from None
    if not full.is_file():
        raise Http404

    if _use_x_accel():
        response = HttpResponse(content_type='application/zip')
        prefix = getattr(settings, 'PROTECTED_MEDIA_INTERNAL_URL', '/protected-media/')
        response['X-Accel-Redirect'] = f'{prefix}{quote(rel_path, safe="/")}'
        response['Content-Disposition'] = (
            f'attachment; filename="{get_valid_filename(filename)}"'
        )
    else:
        response = FileResponse(
            full.open('rb'),
            as_attachment=True,
            filename=get_valid_filename(filename),
            content_type='application/zip',
        )
    response['X-Content-Type-Options'] = 'nosniff'
    return response
