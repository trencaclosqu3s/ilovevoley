from collections import Counter, defaultdict
import logging
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, F, Max, Q, Window
from django.db.models.functions import RowNumber
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from ilovevoley.competitions.models import League, Match
from ilovevoley.core.mixins import get_club_team_filter
from ilovevoley.core.models import Category, Season
from ilovevoley.core.season_utils import resolve_season_filter
from ilovevoley.core.tenancy import get_tenant_object_or_404
from ilovevoley.core.tenant_utils import (
    can_moderate_images,
    can_tag_image,
    tenant_access_required,
    user_is_tenant_manager,
)
from ilovevoley.rosters.models import Person
from ilovevoley.teams.models import Team
from ilovevoley.core.email_utils import enqueue_on_commit
from .services import apply_image_tags, moderate_image, taggable_persons
from .forms import (
    CommentForm,
    ImageFilterForm,
    ImageModerationForm,
    ImageUploadForm,
    VideoBulkSharedForm,
    VideoEntryFormSet,
    VideoForm,
)
from .models import Comment, Image, Video
from .services import queue_match_media_push
from .thumbnails import schedule_thumbnail_generation

logger = logging.getLogger(__name__)

POPULAR_TAGS_CACHE_TTL = 3600


def _coerce_set_number(raw):
    """Convierte el valor de un formulario a un set válido (>=1) o None."""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 1 else None


def get_popular_tags(organization, limit=15):
    """Top tags for suggestions; cached per tenant to avoid scanning images each request."""
    cache_key = f'gallery:popular_tags:{organization.pk}'

    def _compute():
        qs = Image.objects.filter(organization=organization, status='approved')
        manual_tags = []
        for tags in qs.exclude(tags='').values_list('tags', flat=True):
            manual_tags.extend(
                [tag.strip().lower() for tag in tags.split(',') if tag.strip()]
            )
        auto_tags = []
        for auto in qs.exclude(auto_tags=[]).values_list('auto_tags', flat=True):
            if isinstance(auto, list):
                auto_tags.extend([tag.lower() for tag in auto])
        all_tags = manual_tags + auto_tags
        if not all_tags:
            return []
        return [tag for tag, _count in Counter(all_tags).most_common(limit)]

    return cache.get_or_set(cache_key, _compute, POPULAR_TAGS_CACHE_TTL)


def gallery_image_stats(organization):
    """Approved/pending/match counts scoped to the current tenant."""
    stats = Image.objects.filter(organization=organization).aggregate(
        total_images=Count('pk', filter=Q(status='approved')),
        pending_images=Count('pk', filter=Q(status='pending')),
        images_with_match=Count(
            'pk', filter=Q(status='approved', match__isnull=False)
        ),
        images_without_match=Count(
            'pk', filter=Q(status='approved', match__isnull=True)
        ),
    )
    return stats


def _covers_by(images_qs, field, ids, *, prefetch=()):
    """Top 4 images per group in one SQL query (ROW_NUMBER + qualify subquery)."""
    if not ids:
        return {}
    qs = (
        images_qs.filter(**{f'{field}__in': ids})
        .annotate(
            rn=Window(
                RowNumber(),
                partition_by=[F(field)],
                order_by=F('upload_date').desc(),
            )
        )
        .filter(rn__lte=4)
        .order_by(field, '-upload_date')
    )
    if prefetch:
        qs = qs.prefetch_related(*prefetch)
    buckets = defaultdict(list)
    for image in qs:
        buckets[getattr(image, field)].append(image)
    return buckets


def build_album_gallery_page(images_qs, page_number, per_page=12):
    """
    Aggregate albums in SQL, paginate lightweight group rows, hydrate covers for the page.
    Returns (page_obj, total_albums, total_single_images).
    """
    # Clear ORDER BY so GROUP BY aggregations stay valid in PostgreSQL.
    images_qs = images_qs.order_by()

    match_groups = list(
        images_qs.filter(match__isnull=False)
        .values('match_id')
        .annotate(image_count=Count('id'), sort_date=Max('match__match_date'))
    )
    for group in match_groups:
        group['type'] = 'album'

    album_groups = list(
        images_qs.filter(match__isnull=True, album_group_id__isnull=False)
        .values('album_group_id')
        .annotate(
            image_count=Count('id'),
            sort_date=Max('upload_date'),
            album_name=Max('album_name'),
        )
    )
    for group in album_groups:
        group['type'] = 'album_group'

    singles = list(
        images_qs.filter(match__isnull=True, album_group_id__isnull=True)
        .values('id', 'upload_date')
    )
    for single in singles:
        single['type'] = 'single'
        single['image_count'] = 1
        single['sort_date'] = single['upload_date']

    all_items = match_groups + album_groups + singles
    all_items.sort(key=lambda item: item['sort_date'] or timezone.now(), reverse=True)

    paginator = Paginator(all_items, per_page)
    page_obj = paginator.get_page(page_number)
    page_rows = list(page_obj.object_list)

    match_ids = [row['match_id'] for row in page_rows if row['type'] == 'album']
    group_ids = [row['album_group_id'] for row in page_rows if row['type'] == 'album_group']
    single_ids = [row['id'] for row in page_rows if row['type'] == 'single']

    matches = {
        match.id: match
        for match in Match.objects.filter(pk__in=match_ids).select_related(
            'home_team', 'away_team', 'league'
        )
    }

    covers_by_match = _covers_by(images_qs, 'match_id', match_ids)
    covers_by_group = _covers_by(
        images_qs, 'album_group_id', group_ids, prefetch=('categories',)
    )

    singles_map = {
        image.id: image
        for image in images_qs.filter(pk__in=single_ids).prefetch_related('categories')
    } if single_ids else {}

    hydrated = []
    for row in page_rows:
        if row['type'] == 'album':
            hydrated.append({
                'type': 'album',
                'match': matches[row['match_id']],
                'images': covers_by_match[row['match_id']],
                'image_count': row['image_count'],
            })
        elif row['type'] == 'album_group':
            hydrated.append({
                'type': 'album_group',
                'album_group_id': row['album_group_id'],
                'album_name': row['album_name'] or _('Álbum'),
                'images': covers_by_group[row['album_group_id']],
                'image_count': row['image_count'],
                'upload_date': row['sort_date'],
            })
        else:
            hydrated.append({
                'type': 'single',
                'image': singles_map[row['id']],
                'image_count': 1,
            })

    page_obj.object_list = hydrated
    return page_obj, len(match_groups) + len(album_groups), len(singles)


@tenant_access_required()
def video_list(request):
    videos = Video.objects.select_related(
        'category', 'created_by', 'match__home_team', 'match__away_team', 'match__league'
    ).prefetch_related('comments').filter(
        organization=request.tenant
    )
    categories = Category.objects.filter(is_active=True)
    leagues = League.objects.for_tenant(request.tenant)
    teams = Team.objects.all()
    seasons = Season.objects.all()
    season_filter, selected_season = resolve_season_filter(request)

    # Filtros
    category_filter = request.GET.get('category')
    league_filter = request.GET.get('league')
    team_filter = request.GET.get('team')
    search_query = request.GET.get('search', '').strip()
    show_all = request.GET.get('show_all', '0') == '1'

    # Filtrar por temporada (activa por defecto)
    if season_filter:
        videos = videos.filter(season=season_filter)
    
    # Filtrar por categorías preferidas del usuario si no se especifica otra cosa
    if not category_filter and not show_all and request.user.has_preferred_categories(request.tenant):
        user_categories = request.user.preferred_categories_for(request.tenant)
        videos = videos.filter(category__in=user_categories)
    
    # Aplicar filtro de categoría
    if category_filter:
        videos = videos.filter(category_id=category_filter)
    
    # Aplicar filtro de liga
    if league_filter:
        videos = videos.filter(match__league_id=league_filter)
    
    # Aplicar filtro de equipo
    if team_filter:
        videos = videos.filter(
            Q(match__home_team_id=team_filter) | 
            Q(match__away_team_id=team_filter)
        )
    
    # Aplicar búsqueda de texto (case-insensitive, accent-insensitive)
    if search_query:
        # Buscar en título, descripción y equipos
        videos = videos.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(match__home_team__name__icontains=search_query) |
            Q(match__away_team__name__icontains=search_query) |
            Q(match__home_team_text__icontains=search_query) |
            Q(match__away_team_text__icontains=search_query)
        )
    
    # Paginación
    paginator = Paginator(videos, 12)  # 12 videos por página
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    can_add = user_is_tenant_manager(request.user, request.tenant)
    
    # Mensaje de prueba para verificar el sistema de toast (solo para desarrollo)
    if request.GET.get('test_toast'):
        test_type = request.GET.get('test_toast')
        if test_type == 'success':
            messages.success(request, _('¡Toast de éxito funcionando correctamente!'))
        elif test_type == 'error':
            messages.error(request, _('Toast de error funcionando correctamente'))
        elif test_type == 'warning':
            messages.warning(request, _('Toast de advertencia funcionando correctamente'))
        elif test_type == 'info':
            messages.info(request, _('Toast de información funcionando correctamente'))
    
    return render(request, 'content/video_list.html', {
        'page_obj': page_obj,
        'categories': categories,
        'leagues': leagues,
        'teams': teams,
        'seasons': seasons,
        'selected_season': selected_season,
        'season_filtered': 'season' in request.GET,
        'selected_category': category_filter,
        'selected_league': league_filter,
        'selected_team': team_filter,
        'search_query': search_query,
        'can_add': can_add,
        'show_all': show_all,
        'has_preferences': request.user.has_preferred_categories(request.tenant),
    })


@tenant_access_required(manager=True)
def video_create(request):
    if request.method == 'POST':
        form = VideoForm(request.POST, organization=request.tenant)
        if form.is_valid():
            video = form.save(commit=False)
            video.created_by = request.user
            video.organization = request.tenant
            video.save()
            if video.match_id and request.tenant:
                queue_match_media_push(match_id=video.match_id, media_type='video', organization_id=request.tenant.id)
            messages.success(request, _('Vídeo añadido correctamente'))
            return redirect('content:video_list')
    else:
        form = VideoForm(organization=request.tenant)

    return render(request, 'content/video_form.html', {'form': form})


@tenant_access_required(manager=True)
def video_bulk_create(request):
    """Crear múltiples vídeos para el mismo partido en un solo formulario."""
    match_id = request.GET.get('match') or request.POST.get('match_hidden')

    if request.method == 'POST':
        shared_form = VideoBulkSharedForm(request.POST, organization=request.tenant)
        formset = VideoEntryFormSet(request.POST, prefix='videos')

        if shared_form.is_valid() and formset.is_valid():
            match = shared_form.cleaned_data.get('match')
            category = shared_form.cleaned_data.get('category')
            created = 0
            for entry in formset.cleaned_data:
                if entry and not entry.get('DELETE') and entry.get('title') and entry.get('youtube_url'):
                    Video.objects.create(
                        title=entry['title'],
                        youtube_url=entry['youtube_url'],
                        match=match,
                        category=category,
                        set_number=entry.get('set_number'),
                        created_by=request.user,
                        organization=request.tenant,
                    )
                    created += 1

            if created:
                if match and request.tenant:
                    queue_match_media_push(match_id=match.id, media_type='video', organization_id=request.tenant.id)
                messages.success(request, _('%(count)s vídeo(s) añadido(s) correctamente.') % {'count': created})
            else:
                messages.warning(request, _('No se añadió ningún vídeo. Rellena al menos un título y URL.'))
                return render(request, 'content/video_bulk_form.html', {
                    'shared_form': shared_form,
                    'formset': formset,
                })

            if match:
                return redirect('competitions:match_detail', match_id=match.id)
            return redirect('content:video_list')
    else:
        initial_shared = {}
        if match_id:
            initial_shared['match'] = match_id
        shared_form = VideoBulkSharedForm(initial=initial_shared, organization=request.tenant)
        formset = VideoEntryFormSet(prefix='videos')

    return render(request, 'content/video_bulk_form.html', {
        'shared_form': shared_form,
        'formset': formset,
        'match_id': match_id,
    })


@tenant_access_required()
def video_detail(request, video_id):
    video = get_tenant_object_or_404(
        Video.objects, request.tenant, user=request.user, id=video_id
    )

    # Manejar envío de comentarios
    if request.method == 'POST':
        comment_form = CommentForm(request.POST)
        if comment_form.is_valid():
            comment = comment_form.save(commit=False)
            comment.video = video
            comment.user = request.user
            comment.save()
            messages.success(request, _('¡Comentario añadido correctamente!'))
            return redirect('content:video_detail', video_id=video.id)
    else:
        comment_form = CommentForm()
    
    # Cargar comentarios con información del usuario
    comments = video.comments.select_related('user').all()
    
    return render(request, 'content/video_detail.html', {
        'video': video,
        'comments': comments,
        'comment_form': comment_form
    })


@tenant_access_required()
def image_gallery(request):
    """Vista de galería de imágenes con filtros"""
    images = Image.objects.select_related(
        'match__home_team', 'match__away_team', 'match__league',
        'uploaded_by'
    ).prefetch_related('categories').filter(
        organization=request.tenant,
        status='approved',
    ).order_by('-upload_date')
    
    # Variable para controlar si mostrar todo el contenido
    show_all = request.GET.get('show_all', '0') == '1'
    
    # Aplicar filtros
    filter_form = ImageFilterForm(request.GET)
    if filter_form.is_valid():
        search = filter_form.cleaned_data.get('search')
        tags = filter_form.cleaned_data.get('tags')
        image_type = filter_form.cleaned_data.get('image_type')
        match_filter = filter_form.cleaned_data.get('match_filter')
        category = filter_form.cleaned_data.get('category')
        status_filter = filter_form.cleaned_data.get('status')
        
        # Búsqueda general en título, descripción y etiquetas
        if search:
            images = images.filter(
                Q(title__icontains=search) | 
                Q(description__icontains=search) |
                Q(tags__icontains=search)
            )
        
        # Búsqueda específica por etiquetas (incluye auto_tags)
        if tags:
            tag_queries = Q()
            for tag in tags.split(','):
                tag = tag.strip()
                if tag:
                    tag_queries |= (
                        Q(tags__icontains=tag) |
                        Q(auto_tags__icontains=tag)
                    )
            images = images.filter(tag_queries)
        
        # Filtro por tipo de imagen
        if image_type:
            images = images.filter(image_type=image_type)
        
        # Filtro por partido vinculado
        if match_filter == 'with_match':
            images = images.filter(match__isnull=False)
        elif match_filter == 'without_match':
            images = images.filter(match__isnull=True)
        
        if category:
            images = images.filter(categories=category)
        elif not show_all and request.user.has_preferred_categories(request.tenant):
            # Filtrar por preferencias solo si no hay filtro de categoría específico
            user_categories = request.user.preferred_categories_for(request.tenant)
            images = images.filter(categories__in=user_categories).distinct()
            
        if status_filter:
            images = images.filter(status=status_filter)
    else:
        # Si no hay filtros válidos, aplicar preferencias por defecto
        if not show_all and request.user.has_preferred_categories(request.tenant):
            user_categories = request.user.preferred_categories_for(request.tenant)
            images = images.filter(categories__in=user_categories).distinct()

    # Galería "Fotos de X": filtra por deportista etiquetado, acotado al club.
    tagged_person = None
    person_param = request.GET.get('person')
    if person_param and person_param.isdigit():
        tagged_person = Person.objects.for_tenant(request.tenant).filter(
            pk=person_param
        ).first()
        if tagged_person is not None:
            images = images.filter(persons=tagged_person)

    # Filtrar por temporada (activa por defecto)
    season_filter, selected_season = resolve_season_filter(request)
    if season_filter:
        images = images.filter(season=season_filter)

    # Paginación
    paginator = Paginator(images, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    stats = gallery_image_stats(request.tenant)
    popular_tags = get_popular_tags(request.tenant)

    context = {
        'page_obj': page_obj,
        'filter_form': filter_form,
        'seasons': Season.objects.all(),
        'selected_season': selected_season,
        'total_images': stats['total_images'],
        'pending_images': stats['pending_images'],
        'images_with_match': stats['images_with_match'],
        'images_without_match': stats['images_without_match'],
        'popular_tags': popular_tags,
        'current_filters': request.GET.dict(),
        'show_all': show_all,
        'has_preferences': request.user.has_preferred_categories(request.tenant),
        'view_mode': 'individual',
        'tagged_person': tagged_person,
    }

    return render(request, 'content/image_gallery.html', context)


@tenant_access_required()
def image_gallery_albums(request):
    """Vista de galería de imágenes agrupadas por partido (álbumes)"""
    # Obtener imágenes con sus partidos relacionados
    images = Image.objects.select_related(
        'match__home_team', 'match__away_team', 'match__league',
        'uploaded_by'
    ).prefetch_related('categories').filter(
        organization=request.tenant,
        status='approved',
    ).order_by('-upload_date')
    
    # Variable para controlar si mostrar todo el contenido
    show_all = request.GET.get('show_all', '0') == '1'
    
    # Aplicar filtros (reutilizar lógica de image_gallery)
    filter_form = ImageFilterForm(request.GET)
    if filter_form.is_valid():
        search = filter_form.cleaned_data.get('search')
        tags = filter_form.cleaned_data.get('tags')
        image_type = filter_form.cleaned_data.get('image_type')
        match_filter = filter_form.cleaned_data.get('match_filter')
        category = filter_form.cleaned_data.get('category')
        status_filter = filter_form.cleaned_data.get('status')
        
        # Búsqueda general en título, descripción y etiquetas
        if search:
            images = images.filter(
                Q(title__icontains=search) | 
                Q(description__icontains=search) |
                Q(tags__icontains=search)
            )
        
        # Búsqueda específica por etiquetas (incluye auto_tags)
        if tags:
            tag_queries = Q()
            for tag in tags.split(','):
                tag = tag.strip()
                if tag:
                    tag_queries |= (
                        Q(tags__icontains=tag) |
                        Q(auto_tags__icontains=tag)
                    )
            images = images.filter(tag_queries)
        
        # Filtro por tipo de imagen
        if image_type:
            images = images.filter(image_type=image_type)
        
        # Filtro por partido vinculado
        if match_filter == 'with_match':
            images = images.filter(match__isnull=False)
        elif match_filter == 'without_match':
            images = images.filter(match__isnull=True)
        
        if category:
            images = images.filter(categories=category)
        elif not show_all and request.user.has_preferred_categories(request.tenant):
            # Filtrar por preferencias solo si no hay filtro de categoría específico
            user_categories = request.user.preferred_categories_for(request.tenant)
            images = images.filter(categories__in=user_categories).distinct()
            
        if status_filter:
            images = images.filter(status=status_filter)
    else:
        # Si no hay filtros válidos, aplicar preferencias por defecto
        if not show_all and request.user.has_preferred_categories(request.tenant):
            user_categories = request.user.preferred_categories_for(request.tenant)
            images = images.filter(categories__in=user_categories).distinct()

    # Filtrar por temporada (activa por defecto)
    season_filter, selected_season = resolve_season_filter(request)
    if season_filter:
        images = images.filter(season=season_filter)

    page_obj, total_albums, total_single_images = build_album_gallery_page(
        images, request.GET.get('page')
    )
    stats = gallery_image_stats(request.tenant)
    popular_tags = get_popular_tags(request.tenant)

    context = {
        'page_obj': page_obj,
        'filter_form': filter_form,
        'seasons': Season.objects.all(),
        'selected_season': selected_season,
        'total_images': stats['total_images'],
        'pending_images': stats['pending_images'],
        'total_albums': total_albums,
        'total_single_images': total_single_images,
        'popular_tags': popular_tags,
        'current_filters': request.GET.dict(),
        'show_all': show_all,
        'has_preferences': request.user.has_preferred_categories(request.tenant),
        'view_mode': 'albums',
    }

    return render(request, 'content/image_gallery.html', context)


@tenant_access_required()
def image_upload(request):
    """Vista para subir imágenes"""
    if request.method == 'POST':
        form = ImageUploadForm(request.POST, request.FILES, organization=request.tenant)
        if form.is_valid():
            image = form.save(commit=False)
            image.uploaded_by = request.user
            image.organization = request.tenant

            # Si el usuario es superuser, aprobar directamente sin pasar por Vision API
            enqueue_vision = False
            if request.user.is_superuser:
                image.status = 'approved'
                image.moderated_by = request.user
                image.moderation_date = timezone.now()
                image.moderation_notes = _('Aprobada automáticamente por superusuario')
                image.vision_api_checked = False
                image.vision_api_safe = True
                image.vision_api_details = {'skipped': 'Superuser approval - bypassed Vision API'}
                logger.info(f"Imagen aprobada automáticamente para superusuario {request.user.username}")
            elif getattr(settings, 'GOOGLE_VISION_ENABLED', False):
                # Vision en Celery tras commit; el signal no debe avisar hasta el resultado
                image._skip_pending_email = True
                enqueue_vision = True

            image.save()
            if enqueue_vision:
                from ilovevoley.content.tasks import analyze_image_with_vision_task
                enqueue_on_commit(analyze_image_with_vision_task, image.id, True)

            try:
                schedule_thumbnail_generation(image)
            except Exception as e:
                logger.error(f"Error generando miniaturas para '{image.title}': {e}")

            # Asignar categorías
            categories_to_add = []
            
            # Prioridad 1: Si hay match, usar categorías del partido
            if image.match:
                match = image.match
                if match.home_team and match.home_team.category:
                    categories_to_add.append(match.home_team.category)
                if match.away_team and match.away_team.category:
                    categories_to_add.append(match.away_team.category)
                if match.league:
                    categories_to_add.extend(list(match.league.categories.all()))
            
            # Prioridad 2: Si no hay match, usar categorías seleccionadas manualmente
            if not categories_to_add:
                category_ids = form.cleaned_data.get('categories', [])
                if category_ids:
                    categories_to_add = list(category_ids)
            
            # Asignar categorías (eliminar duplicados)
            if categories_to_add:
                # Convertir a set para eliminar duplicados, luego a list
                unique_categories = list(set(categories_to_add))
                image.categories.set(unique_categories)
            
            # Mensaje dinámico según el estado de la imagen
            if image.status == 'approved':
                auto_tags_msg = (
                    _(' Se detectaron automáticamente las etiquetas: %(tags)s.') % {'tags': ', '.join(image.auto_tags[:3])}
                ) if image.auto_tags else ''
                messages.success(request, _('Imagen subida y aprobada automáticamente.') + auto_tags_msg)
            else:
                auto_tags_msg = (
                    _(' Se detectaron automáticamente las etiquetas: %(tags)s.') % {'tags': ', '.join(image.auto_tags[:3])}
                ) if image.auto_tags else ''
                messages.success(request, _('Imagen subida correctamente. Está pendiente de moderación.') + auto_tags_msg)

            # Solo se avisa de contenido ya visible: `match_detail` únicamente muestra
            # imágenes aprobadas. Una imagen pendiente se avisa al aprobarse (Vision o
            # moderación), no en la subida.
            if image.status == 'approved' and image.match_id and request.tenant:
                queue_match_media_push(match_id=image.match_id, media_type='photo', organization_id=request.tenant.id)

            return redirect('content:image_gallery')
        else:
            # El formulario no es válido, mostrar errores
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, _('%(field)s: %(error)s') % {'field': field, 'error': error})
    else:
        # Pre-cargar partido si se pasa en la URL
        initial_data = {}
        match_id = request.GET.get('match')
        if match_id:
            try:
                match = Match.objects.get(id=match_id)
                initial_data['match'] = match
            except Match.DoesNotExist:
                pass
        
        form = ImageUploadForm(initial=initial_data, organization=request.tenant)

    # Obtener partidos recientes para sugerir (solo pasados + el próximo)
    club_query = get_club_team_filter(request.tenant)

    now = timezone.now()

    # Partidos del pasado (últimos 10)
    # (withdrawn excluidos automáticamente por el manager)
    past_matches = Match.objects.select_related(
        'home_team', 'away_team', 'league'
    ).filter(club_query, match_date__lt=now).order_by('-match_date')[:10]

    # Próximo partido futuro (solo uno)
    next_match = Match.objects.select_related(
        'home_team', 'away_team', 'league'
    ).filter(club_query, match_date__gte=now).order_by('match_date').first()

    # Combinar ambos querysets
    if next_match:
        # Convertir a lista para combinar y ordenar
        recent_matches = list(past_matches) + [next_match]
        recent_matches.sort(key=lambda x: x.match_date, reverse=True)
    else:
        recent_matches = list(past_matches)
    
    context = {
        'form': form,
        'recent_matches': recent_matches,
    }
    
    return render(request, 'content/image_upload.html', context)


@tenant_access_required()
def image_bulk_upload(request):
    """Vista para subir múltiples imágenes a la vez"""
    if request.method == 'POST':
        uploaded_files = request.FILES.getlist('images')
        
        if not uploaded_files:
            messages.error(request, _('No se seleccionaron imágenes.'))
            return redirect('content:image_bulk_upload')
        
        # Datos compartidos para todas las imágenes
        season_id = request.POST.get('season') or None
        shared_data = {
            'uploaded_by': request.user,
            'image_type': request.POST.get('image_type', 'other'),
            'season_id': season_id,
            'set_number': _coerce_set_number(request.POST.get('set_number')),
            'organization': request.tenant,
        }
        
        # Match y categorías opcionales compartidos
        match_id = request.POST.get('match')
        if match_id:
            try:
                shared_data['match'] = Match.objects.get(id=match_id)
            except Match.DoesNotExist:
                pass
        
        # Verificar si se está agregando a álbum existente
        album_group_id = None
        album_name = ''
        create_album = False
        existing_album_id = request.POST.get('existing_album_id')
        if existing_album_id and not match_id:
            try:
                album_uuid = uuid.UUID(existing_album_id)
                # Verificar que álbum existe
                existing_images = Image.objects.filter(album_group_id=album_uuid)
                if existing_images.exists():
                    album_group_id = album_uuid
                    album_name = existing_images.first().album_name or _('Álbum')
                    shared_data['album_group_id'] = album_group_id
                    shared_data['album_name'] = album_name
                else:
                    messages.error(request, _('El álbum especificado no existe.'))
                    return redirect('content:image_bulk_upload')
            except (ValueError, ValidationError):
                messages.error(request, _('ID de álbum inválido.'))
                return redirect('content:image_bulk_upload')
        else:
            # Código original: crear nuevo álbum si se marca
            create_album = request.POST.get('create_album') == 'on'
            album_name = request.POST.get('album_name', '').strip()
            if create_album and not match_id:
                if not album_name:
                    messages.error(request, _('El nombre del álbum es obligatorio cuando se agrupan imágenes.'))
                    return redirect('content:image_bulk_upload')
                album_group_id = uuid.uuid4()
                shared_data['album_group_id'] = album_group_id
                shared_data['album_name'] = album_name
        
        # Etiquetas compartidas
        shared_tags = request.POST.get('tags', '').strip()
        
        # Procesar cada imagen de forma optimizada
        success_count = 0
        approved_count = 0
        errors = []
        pending_ids = []
        vision_ids = []

        for idx, uploaded_file in enumerate(uploaded_files):
            try:
                # Validar tipo y tamaño de archivo
                content_type = getattr(uploaded_file, 'content_type', '') or ''
                if not content_type.startswith('image/'):
                    errors.append(_('%(name)s: No es una imagen válida') % {'name': uploaded_file.name})
                    continue

                if uploaded_file.size > 10 * 1024 * 1024:  # 10MB
                    errors.append(_('%(name)s: Archivo demasiado grande (máx 10MB)') % {'name': uploaded_file.name})
                    continue

                # Obtener título y descripción individual
                title = request.POST.get(f'title_{idx}', uploaded_file.name.rsplit('.', 1)[0])
                description = request.POST.get(f'description_{idx}', '')

                # Crear imagen
                image = Image(
                    image=uploaded_file,
                    title=title,
                    description=description,
                    tags=shared_tags,
                    **shared_data
                )

                # Si el usuario es superuser, aprobar directamente sin pasar por Vision API
                enqueue_vision = False
                if request.user.is_superuser:
                    image.status = 'approved'
                    image.moderated_by = request.user
                    image.moderation_date = timezone.now()
                    image.moderation_notes = _('Aprobada automáticamente por superusuario')
                    image.vision_api_checked = False
                    image.vision_api_safe = True
                    image.vision_api_details = {'skipped': 'Superuser approval - bypassed Vision API'}
                    logger.info(f"Imagen aprobada automáticamente para superusuario {request.user.username}")
                else:
                    # Bulk: nunca N emails individuales; Vision en background si está habilitado
                    image._skip_pending_email = True
                    if getattr(settings, 'GOOGLE_VISION_ENABLED', False):
                        enqueue_vision = True

                # Guardar imagen
                image.save()
                if image.status == 'pending':
                    pending_ids.append(image.id)
                elif image.status == 'approved':
                    approved_count += 1
                if enqueue_vision:
                    vision_ids.append(image.id)

                try:
                    schedule_thumbnail_generation(image)
                except Exception as e:
                    logger.error(f"Error generando miniaturas para '{title}': {e}")

                # Asignar categorías
                categories_to_add = []

                # Prioridad 1: Si hay match, usar categorías del partido
                if 'match' in shared_data and shared_data['match']:
                    match = shared_data['match']
                    if match.home_team and match.home_team.category:
                        categories_to_add.append(match.home_team.category)
                    if match.away_team and match.away_team.category:
                        categories_to_add.append(match.away_team.category)
                    if match.league:
                        categories_to_add.extend(list(match.league.categories.all()))

                # Prioridad 2: Si no hay match, usar categorías seleccionadas manualmente
                if not categories_to_add:
                    category_ids = request.POST.getlist('categories')
                    if category_ids:
                        categories_to_add = Category.objects.filter(id__in=category_ids)

                # Asignar categorías (eliminar duplicados)
                if categories_to_add:
                    # Convertir a set para eliminar duplicados, luego a list
                    unique_categories = list(set(categories_to_add))
                    image.categories.set(unique_categories)

                success_count += 1
                logger.info(f"Imagen subida exitosamente: {title} por {request.user.username}")

            except Exception as e:
                logger.error(f"Error procesando {uploaded_file.name}: {str(e)}")
                errors.append(_('%(name)s: %(error)s') % {'name': uploaded_file.name, 'error': str(e)})

        if vision_ids or pending_ids:
            from ilovevoley.content.tasks import analyze_image_with_vision_task
            from ilovevoley.core.tasks import notify_images_pending_batch_task

            vision_ids_copy = list(vision_ids)
            pending_ids_copy = list(pending_ids)

            def _enqueue_bulk_followups():
                for image_id in vision_ids_copy:
                    analyze_image_with_vision_task.delay(image_id, False)
                if pending_ids_copy and settings.EMAIL_NOTIFICATIONS.get('image_pending', True):
                    notify_images_pending_batch_task.delay(pending_ids_copy)

            from django.db import transaction
            transaction.on_commit(_enqueue_bulk_followups)

        # Mensajes de resultado
        if success_count > 0:
            messages.success(request, _('✅ %(count)s imagen(es) subida(s) correctamente.') % {'count': success_count})

        if errors:
            for error in errors[:5]:  # Mostrar máximo 5 errores
                messages.warning(request, error)
            if len(errors) > 5:
                messages.warning(request, _('... y %(count)s error(es) más.') % {'count': len(errors) - 5})

        if success_count > 0:
            # Despachar notificación push asíncrona al club si se creó un nuevo álbum
            tenant = getattr(request, 'tenant', None)
            if tenant and create_album and not match_id:
                from ilovevoley.core.i18n import push_message
                from ilovevoley.users.tasks import notify_web_push_organization_task
                album_url = (
                    reverse('content:album_group_images', args=[album_group_id])
                    if album_group_id
                    else reverse('content:image_gallery')
                )
                notify_web_push_organization_task.delay(
                    organization_id=tenant.id,
                    **push_message(lambda: (
                        _('Nuevo Álbum'),
                        _('Se han subido nuevas fotos: %(album)s') % {'album': album_name}
                        if album_name else _('Se han subido nuevas fotos'),
                    )),
                    url=album_url,
                    category_ids=[int(c) for c in request.POST.getlist('categories') if c.isdigit()],
                    notification_type='new_album',
                )

            # Solo se avisa si hay alguna imagen ya visible en el partido: las
            # pendientes de moderación avisan al aprobarse (#286).
            if tenant and match_id and approved_count:
                try:
                    queue_match_media_push(match_id=int(match_id), media_type='photo', organization_id=tenant.id)
                except (TypeError, ValueError):
                    pass

            # Redirigir al álbum si se agregaron fotos a uno existente
            existing_album_id = request.POST.get('existing_album_id')
            if existing_album_id:
                messages.success(
                    request,
                    _('✅ %(count)s imagen(es) agregada(s) al álbum correctamente.') % {'count': success_count}
                )
                return redirect('content:album_group_images', album_group_id=existing_album_id)
            else:
                return redirect('content:image_gallery')
        else:
            return redirect('content:image_bulk_upload')
    
    # GET request
    # Pre-cargar álbum existente si se proporciona en URL
    existing_album = None
    album_group_id_param = request.GET.get('album_group_id')
    if album_group_id_param:
        try:
            # Validar formato UUID
            album_uuid = uuid.UUID(album_group_id_param)

            # Verificar que el álbum existe
            album_images = Image.objects.filter(
                album_group_id=album_uuid
            ).select_related('uploaded_by')

            if album_images.exists():
                first_image = album_images.first()
                existing_album = {
                    'album_group_id': str(album_uuid),
                    'album_name': first_image.album_name or _('Álbum'),
                    'image_count': album_images.count(),
                    'upload_date': first_image.upload_date,
                }
        except (ValueError, ValidationError):
            # UUID inválido, ignorar
            pass

    # Pre-cargar partido si se pasa en la URL
    selected_match = None
    match_id = request.GET.get('match')
    if match_id:
        try:
            selected_match = Match.objects.get(id=match_id)
        except Match.DoesNotExist:
            pass
    
    # Obtener partidos recientes para sugerir (solo pasados + el próximo)
    club_query = get_club_team_filter(request.tenant)

    now = timezone.now()

    # Partidos del pasado (últimos 10)
    # (withdrawn excluidos automáticamente por el manager)
    past_matches = Match.objects.select_related(
        'home_team', 'away_team', 'league'
    ).filter(club_query, match_date__lt=now).order_by('-match_date')[:10]

    # Próximo partido futuro (solo uno)
    next_match = Match.objects.select_related(
        'home_team', 'away_team', 'league'
    ).filter(club_query, match_date__gte=now).order_by('match_date').first()

    # Combinar ambos querysets
    if next_match:
        # Convertir a lista para combinar y ordenar
        recent_matches = list(past_matches) + [next_match]
        recent_matches.sort(key=lambda x: x.match_date, reverse=True)
    else:
        recent_matches = list(past_matches)

    # Obtener categorías activas
    categories = Category.objects.filter(is_active=True).order_by('name')

    # Tipos de imagen
    image_types = Image.IMAGE_TYPES

    context = {
        'recent_matches': recent_matches,
        'categories': categories,
        'image_types': image_types,
        'seasons': Season.objects.all(),
        'current_season': Season.objects.current(),
        'selected_match': selected_match,
        'existing_album': existing_album,
    }

    return render(request, 'content/image_bulk_upload.html', context)


@tenant_access_required()
def image_detail(request, image_id):
    """Vista de detalle de imagen"""
    image = get_tenant_object_or_404(
        Image.objects.select_related(
            'match__home_team', 'match__away_team', 'match__league',
            'uploaded_by', 'moderated_by'
        ).prefetch_related('categories'),
        request.tenant, user=request.user, id=image_id,
    )

    # Solo mostrar imágenes aprobadas a usuarios normales (managers/admins del tenant pueden ver pendientes)
    if not user_is_tenant_manager(request.user, request.tenant) and image.status != 'approved':
        messages.error(request, _('Imagen no disponible.'))
        return redirect('content:image_gallery')
    
    # Imágenes relacionadas del mismo partido
    related_images = Image.objects.for_tenant(request.tenant).filter(
        match=image.match,
        status='approved'
    ).exclude(id=image.id)[:6]

    can_tag = can_tag_image(request.user, request.tenant, image)
    context = {
        'image': image,
        'related_images': related_images,
        'tagged_persons': image.persons.all().order_by('last_name', 'first_name'),
        'can_tag': can_tag,
        'taggable_persons': taggable_persons(image.match, request.tenant) if can_tag else [],
        'selected_person_ids': set(image.persons.values_list('id', flat=True)),
    }

    return render(request, 'content/image_detail.html', context)


@tenant_access_required()
@require_POST
def image_tag(request, image_id):
    """Guarda las etiquetas de deportistas de una imagen individual."""
    image = get_tenant_object_or_404(Image.objects, request.tenant, id=image_id)

    if not can_tag_image(request.user, request.tenant, image):
        raise PermissionDenied

    person_ids = request.POST.getlist('person_ids')
    # Solo se etiquetan fichas del club: `for_tenant` descarta ids de otro tenant.
    persons = Person.objects.for_tenant(request.tenant).filter(pk__in=person_ids)
    apply_image_tags(
        request.user, request.tenant, [image], persons,
        replace=request.POST.get('action') != 'add',
    )

    messages.success(request, _('Etiquetas actualizadas.'))
    return redirect('content:image_detail', image_id=image.id)


@tenant_access_required(staff=True)
def image_tag_bulk(request):
    """Etiquetado en lote de las imágenes de un partido o álbum."""
    match = None
    images = Image.objects.for_tenant(request.tenant).filter(status='approved').order_by('-upload_date')

    match_id = request.GET.get('match') or request.POST.get('match')
    album_id = request.GET.get('album') or request.POST.get('album')

    if match_id and match_id.isdigit():
        match = Match.objects.filter(pk=match_id).first()
        if match is None:
            raise Http404(_('Partido no encontrado'))
        images = images.filter(match=match)
        title = f'{match.home_team_display} vs {match.away_team_display}'
    elif album_id:
        images = images.filter(album_group_id=album_id)
        title = images.values_list('album_name', flat=True).first() or _('Álbum')
    else:
        raise Http404(_('No se indicó álbum ni partido'))

    if request.method == 'POST':
        image_ids = request.POST.getlist('image_ids')
        person_ids = request.POST.getlist('person_ids')
        replace = request.POST.get('action') != 'add'
        selected = images.filter(pk__in=image_ids)
        persons = Person.objects.for_tenant(request.tenant).filter(pk__in=person_ids)
        changed = apply_image_tags(
            request.user, request.tenant, selected, persons, replace=replace
        )
        messages.success(
            request,
            _('Etiquetas actualizadas en %(count)s imágenes.') % {'count': changed},
        )
        next_url = request.POST.get('next')
        if next_url:
            return redirect(next_url)
        if match is not None:
            return redirect('content:match_images', match_id=match.id)
        return redirect('content:album_group_images', album_group_id=album_id)

    context = {
        'title': title,
        'match': match,
        'album_group_id': album_id,
        'images': images,
        'taggable_persons': taggable_persons(match, request.tenant),
        'next': request.get_full_path(),
    }
    return render(request, 'content/image_tag_bulk.html', context)


@tenant_access_required()
def match_images(request, match_id):
    """Vista de imágenes de un partido específico"""
    match = get_tenant_object_or_404(
        Match.objects.select_related('home_team', 'away_team', 'league'),
        request.tenant, user=request.user, id=match_id,
    )
    
    images = Image.objects.for_tenant(request.tenant).filter(
        match=match,
        status='approved'
    ).select_related('uploaded_by').order_by('-upload_date')
    
    # Paginación
    paginator = Paginator(images, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'match': match,
        'page_obj': page_obj,
        'all_images': images,
        'total_images': page_obj.paginator.count,
        'download_zip_url': reverse('content:match_album_zip', args=[match.id]),
    }

    return render(request, 'content/match_images.html', context)


@tenant_access_required()
def album_group_images(request, album_group_id):
    """Vista de imágenes de un álbum de grupo (sin partido)"""
    # album_group_id ya viene como UUID desde la URL (gracias al path converter <uuid:album_group_id>)
    images = Image.objects.for_tenant(request.tenant).filter(
        album_group_id=album_group_id,
        status='approved'
    ).select_related('uploaded_by').prefetch_related('categories').order_by('-upload_date')
    
    if not images.exists():
        raise Http404(_("Álbum no encontrado"))
    
    # Obtener información del álbum desde la primera imagen
    first_image = images.first()
    
    # Paginación
    paginator = Paginator(images, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Preparar información del álbum
    album_info = {
        'album_group_id': album_group_id,
        'album_name': first_image.album_name or _('Álbum'),
        'upload_date': first_image.upload_date,
        'categories': first_image.categories.all(),
        'image_type': first_image.get_image_type_display(),
    }
    
    context = {
        'album': album_info,
        'page_obj': page_obj,
        'all_images': images,
        'total_images': page_obj.paginator.count,
        'download_zip_url': reverse(
            'content:album_group_zip', args=[album_group_id],
        ),
    }

    return render(request, 'content/album_group_images.html', context)


# ---------------------------------------------------------------------------
# Vistas de moderación de imágenes
# ---------------------------------------------------------------------------

@tenant_access_required(staff=True)
def image_moderation(request):
    """Vista de moderación para admins y managers del tenant actual."""
    images = Image.objects.select_related(
        'match__home_team', 'match__away_team', 'match__league',
        'uploaded_by'
    ).prefetch_related('categories').filter(status='pending').for_tenant(
        request.tenant
    ).order_by('upload_date')
    
    # Paginación
    paginator = Paginator(images, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'pending_count': page_obj.paginator.count,
    }
    
    return render(request, 'content/image_moderation.html', context)


@tenant_access_required(staff=True)
def image_moderate_action(request, image_id):
    """Acción de moderación individual acotada al tenant actual."""
    image = get_tenant_object_or_404(
        Image.objects, request.tenant, id=image_id, status='pending'
    )
    
    if request.method == 'POST':
        form = ImageModerationForm(request.POST, instance=image)
        if form.is_valid():
            action = form.cleaned_data['action']
            notes = form.cleaned_data['moderation_notes']
            
            moderate_image(
                actor=request.user,
                tenant=request.tenant,
                image=image,
                decision=action,
                notes=notes,
            )
            
            action_text = _('aprobada') if action == 'approve' else _('rechazada')
            messages.success(request, _('Imagen %(action)s correctamente.') % {'action': action_text})
            return redirect('content:image_moderation')
    else:
        form = ImageModerationForm()
    
    context = {
        'image': image,
        'form': form,
    }
    
    return render(request, 'content/image_moderate.html', context)


@tenant_access_required(staff=True)
def image_moderate_bulk(request):
    """Moderación masiva de imágenes acotada al tenant actual."""
    if request.method == 'POST':
        action = request.POST.get('action')
        image_ids = request.POST.getlist('image_ids')
        notes = request.POST.get('notes', '')
        
        if action in ['approve', 'reject'] and image_ids:
            images = Image.objects.filter(
                id__in=image_ids, status='pending'
            ).for_tenant(request.tenant)
            count = 0
            for image in images:
                try:
                    moderate_image(
                        actor=request.user,
                        tenant=request.tenant,
                        image=image,
                        decision=action,
                        notes=notes,
                        validate_permission=False,
                    )
                    count += 1
                except ValueError:
                    continue
            
            action_text = _('aprobadas') if action == 'approve' else _('rechazadas')
            messages.success(request, _('%(count)s imágenes %(action)s.') % {'count': count, 'action': action_text})
        
        return redirect('content:image_moderation')
    
    return redirect('content:image_moderation')


@ratelimit(key='user_or_ip', rate='30/m', block=True)
@login_required
@require_POST
def moderate_image_api(request, image_id):
    """API para moderar una imagen vía AJAX con aislamiento por organización."""
    tenant = getattr(request, 'tenant', None)
    if not can_moderate_images(request.user, tenant):
        return JsonResponse({'success': False, 'error': _('Permiso denegado')}, status=403)

    try:
        if tenant is not None:
            image = Image.objects.get(id=image_id, organization=tenant, status='pending')
        elif request.user.is_superuser:
            image = Image.objects.get(id=image_id, status='pending')
        else:
            return JsonResponse({'success': False, 'error': _('Permiso denegado')}, status=403)

        action = request.POST.get('action')  # 'approve' o 'reject'
        notes = request.POST.get('notes', '')
        
        if action not in ['approve', 'reject']:
            return JsonResponse({
                'success': False,
                'error': _('Acción no válida')
            }, status=400)
        
        moderate_image(
            actor=request.user,
            tenant=tenant,
            image=image,
            decision=action,
            notes=notes,
        )
        
        action_text = _('aprobada') if action == 'approve' else _('rechazada')
        
        return JsonResponse({
            'success': True,
            'message': _('Imagen "%(title)s" %(action)s correctamente') % {'title': image.title, 'action': action_text},
            'image_title': image.title,
            'action': action
        })
        
    except Image.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': _('Imagen no encontrada o ya moderada')
        }, status=404)
    except Exception as e:
        logger.error(f"Error moderando imagen {image_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': _('Error interno del servidor')
        }, status=500)



__all__ = [
    'video_list',
    'video_create',
    'video_bulk_create',
    'video_detail',
    'image_gallery',
    'image_gallery_albums',
    'image_upload',
    'image_bulk_upload',
    'image_detail',
    'match_images',
    'album_group_images',
    'image_moderation',
    'image_moderate_action',
    'image_moderate_bulk',
    'moderate_image_api',
]
