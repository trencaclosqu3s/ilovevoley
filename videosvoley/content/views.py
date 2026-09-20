from collections import Counter
import logging
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from videosvoley.competitions.models import League, Match
from videosvoley.core.mixins import get_club_team_filter
from videosvoley.core.models import Category
from videosvoley.core.tenant_utils import tenant_access_required, user_is_tenant_manager
from videosvoley.teams.models import Team
from videosvoley.videos.utils import (
    check_image_with_vision_api,
    process_uploaded_image,
    process_vision_tags_for_volleyball,
)
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

logger = logging.getLogger(__name__)


@tenant_access_required()
def video_list(request):
    videos = Video.objects.select_related(
        'category', 'created_by', 'match__home_team', 'match__away_team', 'match__league'
    ).prefetch_related('comments').filter(
        organization=request.tenant
    )
    categories = Category.objects.filter(is_active=True)
    leagues = League.objects.visible_in_app()
    teams = Team.objects.all()
    
    # Filtros
    category_filter = request.GET.get('category')
    league_filter = request.GET.get('league')
    team_filter = request.GET.get('team')
    search_query = request.GET.get('search', '').strip()
    show_all = request.GET.get('show_all', '0') == '1'
    
    # Filtrar por categorías preferidas del usuario si no se especifica otra cosa
    if not category_filter and not show_all and request.user.preferred_categories.exists():
        user_categories = request.user.preferred_categories.all()
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
            messages.success(request, '¡Toast de éxito funcionando correctamente!')
        elif test_type == 'error':
            messages.error(request, 'Toast de error funcionando correctamente')
        elif test_type == 'warning':
            messages.warning(request, 'Toast de advertencia funcionando correctamente')
        elif test_type == 'info':
            messages.info(request, 'Toast de información funcionando correctamente')
    
    return render(request, 'content/video_list.html', {
        'page_obj': page_obj,
        'categories': categories,
        'leagues': leagues,
        'teams': teams,
        'selected_category': category_filter,
        'selected_league': league_filter,
        'selected_team': team_filter,
        'search_query': search_query,
        'can_add': can_add,
        'show_all': show_all,
        'has_preferences': request.user.preferred_categories.exists(),
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
            messages.success(request, 'Vídeo añadido correctamente')
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
                        created_by=request.user,
                        organization=request.tenant,
                    )
                    created += 1

            if created:
                messages.success(request, f'{created} vídeo(s) añadido(s) correctamente.')
            else:
                messages.warning(request, 'No se añadió ningún vídeo. Rellena al menos un título y URL.')
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
    video = get_object_or_404(Video, id=video_id)
    if video.organization != request.tenant and not request.user.is_superuser:
        raise Http404

    # Manejar envío de comentarios
    if request.method == 'POST':
        comment_form = CommentForm(request.POST)
        if comment_form.is_valid():
            comment = comment_form.save(commit=False)
            comment.video = video
            comment.user = request.user
            comment.save()
            messages.success(request, '¡Comentario añadido correctamente!')
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
        year = filter_form.cleaned_data.get('year')
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
        elif not show_all and request.user.preferred_categories.exists():
            # Filtrar por preferencias solo si no hay filtro de categoría específico
            user_categories = request.user.preferred_categories.all()
            images = images.filter(categories__in=user_categories).distinct()
            
        if year:
            images = images.filter(year=year)
            
        if status_filter:
            images = images.filter(status=status_filter)
    else:
        # Si no hay filtros válidos, aplicar preferencias por defecto
        if not show_all and request.user.preferred_categories.exists():
            user_categories = request.user.preferred_categories.all()
            images = images.filter(categories__in=user_categories).distinct()
    
    # Paginación
    paginator = Paginator(images, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Estadísticas para la vista
    total_images = Image.objects.filter(status='approved').count()
    pending_images = Image.objects.filter(status='pending').count()
    images_with_match = Image.objects.filter(status='approved', match__isnull=False).count()
    images_without_match = Image.objects.filter(status='approved', match__isnull=True).count()
    
    # Obtener etiquetas populares para sugerencias
    popular_tags = []
    try:
        # Recopilar todas las etiquetas manuales
        manual_tags = []
        for image in Image.objects.filter(status='approved').exclude(tags=''):
            manual_tags.extend([tag.strip().lower() for tag in image.tags.split(',') if tag.strip()])
        
        # Recopilar etiquetas automáticas
        auto_tags = []
        for image in Image.objects.filter(status='approved').exclude(auto_tags=[]):
            if isinstance(image.auto_tags, list):
                auto_tags.extend([tag.lower() for tag in image.auto_tags])
        
        # Combinar y contar frecuencias
        all_tags = manual_tags + auto_tags
        if all_tags:
            tag_counts = Counter(all_tags)
            popular_tags = [tag for tag, count in tag_counts.most_common(15)]
    except Exception as e:
        print(f"Error obteniendo etiquetas populares: {e}")
    
    context = {
        'page_obj': page_obj,
        'filter_form': filter_form,
        'total_images': total_images,
        'pending_images': pending_images,
        'images_with_match': images_with_match,
        'images_without_match': images_without_match,
        'popular_tags': popular_tags,
        'current_filters': request.GET.dict(),
        'show_all': show_all,
        'has_preferences': request.user.preferred_categories.exists(),
        'view_mode': 'individual',
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
        year = filter_form.cleaned_data.get('year')
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
        elif not show_all and request.user.preferred_categories.exists():
            # Filtrar por preferencias solo si no hay filtro de categoría específico
            user_categories = request.user.preferred_categories.all()
            images = images.filter(categories__in=user_categories).distinct()
            
        if year:
            images = images.filter(year=year)
            
        if status_filter:
            images = images.filter(status=status_filter)
    else:
        # Si no hay filtros válidos, aplicar preferencias por defecto
        if not show_all and request.user.preferred_categories.exists():
            user_categories = request.user.preferred_categories.all()
            images = images.filter(categories__in=user_categories).distinct()
    
    # Agrupar imágenes por partido
    albums = []
    
    # Obtener imágenes con partido
    images_with_match = images.filter(match__isnull=False)
    
    # Agrupar por partido
    match_groups = {}
    for image in images_with_match:
        match_id = image.match.id
        if match_id not in match_groups:
            match_groups[match_id] = {
                'match': image.match,
                'images': [],
                'image_count': 0
            }
        match_groups[match_id]['images'].append(image)
        match_groups[match_id]['image_count'] += 1
    
    # Convertir a lista y ordenar por fecha del partido
    albums = list(match_groups.values())
    albums.sort(key=lambda x: x['match'].match_date, reverse=True)
    
    # Obtener imágenes sin partido
    images_without_match = images.filter(match__isnull=True)
    
    # Agrupar imágenes sin partido por album_group_id
    album_group_groups = {}
    single_images = []
    
    for image in images_without_match:
        if image.album_group_id:
            # Agrupar por album_group_id
            group_id = str(image.album_group_id)
            if group_id not in album_group_groups:
                album_group_groups[group_id] = {
                    'album_group_id': image.album_group_id,
                    'album_name': image.album_name or 'Álbum',
                    'images': [],
                    'image_count': 0,
                    'upload_date': image.upload_date  # Usar fecha de primera imagen para ordenar
                }
            album_group_groups[group_id]['images'].append(image)
            album_group_groups[group_id]['image_count'] += 1
            # Actualizar fecha si es más reciente (para ordenar por la más reciente)
            if image.upload_date > album_group_groups[group_id]['upload_date']:
                album_group_groups[group_id]['upload_date'] = image.upload_date
        else:
            # Imagen individual sin grupo
            single_images.append(image)
    
    # Convertir grupos de album_group_id a lista de álbumes
    album_groups = list(album_group_groups.values())
    album_groups.sort(key=lambda x: x['upload_date'], reverse=True)
    
    # Paginación para álbumes - mezclar álbumes de partidos, álbumes de grupos e imágenes individuales
    all_items = []
    
    # Agregar álbumes de partidos
    for album in albums:
        all_items.append({
            'type': 'album',
            'match': album['match'],
            'images': album['images'],
            'image_count': album['image_count']
        })
    
    # Agregar álbumes de grupos (sin partido)
    for album_group in album_groups:
        all_items.append({
            'type': 'album_group',
            'album_group_id': album_group['album_group_id'],
            'album_name': album_group['album_name'],
            'images': album_group['images'],
            'image_count': album_group['image_count'],
            'upload_date': album_group['upload_date']
        })
    
    # Agregar imágenes individuales
    for image in single_images:
        all_items.append({
            'type': 'single',
            'image': image,
            'image_count': 1
        })
    
    # Ordenar por fecha
    def get_sort_date(item):
        if item['type'] == 'album':
            return item['match'].match_date
        elif item['type'] == 'album_group':
            return item['upload_date']
        else:
            return item['image'].upload_date
    
    all_items.sort(key=get_sort_date, reverse=True)
    
    paginator = Paginator(all_items, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Estadísticas para la vista
    total_images = Image.objects.filter(status='approved').count()
    pending_images = Image.objects.filter(status='pending').count()
    total_albums = len(albums) + len(album_groups)  # Incluir álbumes de grupos
    total_single_images = len(single_images)
    
    # Obtener etiquetas populares para sugerencias
    popular_tags = []
    try:
        # Recopilar todas las etiquetas manuales
        manual_tags = []
        for image in Image.objects.filter(status='approved').exclude(tags=''):
            manual_tags.extend([tag.strip().lower() for tag in image.tags.split(',') if tag.strip()])
        
        # Recopilar etiquetas automáticas
        auto_tags = []
        for image in Image.objects.filter(status='approved').exclude(auto_tags=[]):
            if isinstance(image.auto_tags, list):
                auto_tags.extend([tag.lower() for tag in image.auto_tags])
        
        # Combinar y contar frecuencias
        all_tags = manual_tags + auto_tags
        if all_tags:
            tag_counts = Counter(all_tags)
            popular_tags = [tag for tag, count in tag_counts.most_common(15)]
    except Exception as e:
        print(f"Error obteniendo etiquetas populares: {e}")
    
    context = {
        'page_obj': page_obj,
        'filter_form': filter_form,
        'total_images': total_images,
        'pending_images': pending_images,
        'total_albums': total_albums,
        'total_single_images': total_single_images,
        'popular_tags': popular_tags,
        'current_filters': request.GET.dict(),
        'show_all': show_all,
        'has_preferences': request.user.preferred_categories.exists(),
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

            # Procesar imagen (convertir HEIC si es necesario)
            try:
                uploaded_file = request.FILES.get('image')
                if uploaded_file:
                    processed_file, original_ext, was_converted = process_uploaded_image(uploaded_file)
                    
                    # Actualizar el archivo en la instancia
                    image.image = processed_file
                    image.original_format = original_ext.lstrip('.')
                    image.was_converted = was_converted
                    
                    if was_converted:
                        logger.info(f"Imagen convertida de {original_ext} a JPEG para usuario {request.user.username}")
                        
            except Exception as e:
                logger.error(f"Error procesando imagen: {str(e)}")
                messages.error(request, f'Error al procesar la imagen: {str(e)}')
                
                # Preparar recent_matches con la misma lógica
                club_query = get_club_team_filter(request.tenant)
                now = timezone.now()
                past_matches = Match.objects.select_related(
                    'home_team', 'away_team', 'league'
                ).filter(club_query, match_date__lt=now).order_by('-match_date')[:10]
                next_match = Match.objects.select_related(
                    'home_team', 'away_team', 'league'
                ).filter(club_query, match_date__gte=now).order_by('match_date').first()
                
                if next_match:
                    recent_matches = list(past_matches) + [next_match]
                    recent_matches.sort(key=lambda x: x.match_date, reverse=True)
                else:
                    recent_matches = list(past_matches)
                
                return render(request, 'content/image_upload.html', {
                    'form': form,
                    'recent_matches': recent_matches
                })
            
            # Si el usuario es superuser, aprobar directamente sin pasar por Vision API
            if request.user.is_superuser:
                image.status = 'approved'
                image.moderated_by = request.user
                image.moderation_date = timezone.now()
                image.moderation_notes = 'Aprobada automáticamente por superusuario'
                image.vision_api_checked = False
                image.vision_api_safe = True
                image.vision_api_details = {'skipped': 'Superuser approval - bypassed Vision API'}
                logger.info(f"Imagen aprobada automáticamente para superusuario {request.user.username}")
            # Procesar con Google Vision API si está habilitado
            elif getattr(settings, 'GOOGLE_VISION_ENABLED', False):
                try:
                    logger.info(f"Procesando imagen con Google Vision API para usuario {request.user.username}")
                    vision_result = check_image_with_vision_api(image.image, extract_labels=True, extract_text=True)
                    
                    image.vision_api_checked = True
                    image.vision_api_safe = vision_result.get('safe', False)
                    image.vision_api_details = vision_result
                    
                    # Procesar etiquetas automáticas si se detectaron
                    detected_labels = vision_result.get('labels', [])
                    detected_text = vision_result.get('text', '')
                    
                    if detected_labels or detected_text:
                        auto_tags = process_vision_tags_for_volleyball(detected_labels, detected_text)
                        # Establecer las etiquetas automáticas directamente
                        image.auto_tags = auto_tags
                        logger.info(f"Etiquetas detectadas: {auto_tags}")
                    
                    # Auto-aprobar SOLO si es segura, la API funcionó correctamente y la moderación automática está habilitada
                    if (vision_result.get('safe', False) and 
                        vision_result.get('details', {}).get('api_response_ok', False) and
                        getattr(settings, 'AUTO_MODERATION_ENABLED', False)):
                        image.status = 'approved'
                        image.moderated_by = request.user
                        image.moderation_date = timezone.now()
                        image.moderation_notes = 'Auto-aprobada por Google Vision API'
                        logger.info(f"Imagen auto-aprobada para usuario {request.user.username}")
                    else:
                        logger.info(f"Imagen requiere moderación manual (safe={vision_result.get('safe')}, auto_mod={getattr(settings, 'AUTO_MODERATION_ENABLED', False)})")
                        
                except Exception as e:
                    # Log error detallado y marcar como que requiere revisión manual
                    logger.error(
                        f"Error en Vision API al procesar imagen para usuario {request.user.username}: {str(e)}", 
                        exc_info=True,
                        extra={
                            'user': request.user.username,
                            'image_title': image.title if hasattr(image, 'title') else 'N/A'
                        }
                    )
                    
                    image.vision_api_checked = False
                    image.vision_api_safe = False
                    image.vision_api_details = {
                        'error': str(e), 
                        'api_response_ok': False,
                        'error_type': type(e).__name__
                    }
                    
                    # En desarrollo, mostrar el error al usuario
                    if settings.DEBUG:
                        messages.warning(
                            request, 
                            f'Error al procesar con Vision API: {str(e)}. La imagen quedará pendiente de moderación manual.'
                        )
                    
                    # En producción, enviar notificación a admins si está configurado
                    if not settings.DEBUG and settings.NOTIFICATION_EMAIL_ENABLED:
                        try:
                            from videosvoley.core.email_utils import send_notification_email
                            send_notification_email(
                                subject='Error en Google Vision API',
                                template_name='emails/vision_api_error.html',
                                context={
                                    'error': str(e),
                                    'user': request.user,
                                    'image_title': image.title if hasattr(image, 'title') else 'N/A',
                                },
                                recipient_list=settings.ADMIN_EMAIL_LIST
                            )
                        except Exception as email_error:
                            logger.error(f"Error al enviar notificación de error de Vision API: {email_error}")
            
            image.save()
            
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
                auto_tags_msg = f" Se detectaron automáticamente las etiquetas: {', '.join(image.auto_tags[:3])}." if image.auto_tags else ""
                messages.success(request, f'Imagen subida y aprobada automáticamente.{auto_tags_msg}')
            else:
                auto_tags_msg = f" Se detectaron automáticamente las etiquetas: {', '.join(image.auto_tags[:3])}." if image.auto_tags else ""
                messages.success(request, f'Imagen subida correctamente. Está pendiente de moderación.{auto_tags_msg}')
            
            return redirect('content:image_gallery')
        else:
            # El formulario no es válido, mostrar errores
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
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
            messages.error(request, 'No se seleccionaron imágenes.')
            return redirect('content:image_bulk_upload')
        
        # Datos compartidos para todas las imágenes
        shared_data = {
            'uploaded_by': request.user,
            'image_type': request.POST.get('image_type', 'other'),
            'year': request.POST.get('year', timezone.now().year),
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
        existing_album_id = request.POST.get('existing_album_id')
        if existing_album_id and not match_id:
            try:
                album_uuid = uuid.UUID(existing_album_id)
                # Verificar que álbum existe
                existing_images = Image.objects.filter(album_group_id=album_uuid)
                if existing_images.exists():
                    album_group_id = album_uuid
                    album_name = existing_images.first().album_name or 'Álbum'
                    shared_data['album_group_id'] = album_group_id
                    shared_data['album_name'] = album_name
                else:
                    messages.error(request, 'El álbum especificado no existe.')
                    return redirect('content:image_bulk_upload')
            except (ValueError, ValidationError):
                messages.error(request, 'ID de álbum inválido.')
                return redirect('content:image_bulk_upload')
        else:
            # Código original: crear nuevo álbum si se marca
            create_album = request.POST.get('create_album') == 'on'
            album_name = request.POST.get('album_name', '').strip()
            if create_album and not match_id:
                if not album_name:
                    messages.error(request, 'El nombre del álbum es obligatorio cuando se agrupan imágenes.')
                    return redirect('content:image_bulk_upload')
                album_group_id = uuid.uuid4()
                shared_data['album_group_id'] = album_group_id
                shared_data['album_name'] = album_name
        
        # Etiquetas compartidas
        shared_tags = request.POST.get('tags', '').strip()
        
        # Procesar cada imagen de forma optimizada
        success_count = 0
        errors = []
        
        # Detectar si es una petición móvil para optimizar procesamiento
        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
        is_mobile_request = any(mobile in user_agent for mobile in ['mobile', 'android', 'iphone', 'ipad'])
        
        for idx, uploaded_file in enumerate(uploaded_files):
            try:
                # Optimizar para móvil si es necesario
                processed_file, original_ext, was_converted = process_uploaded_image(
                    uploaded_file, 
                    optimize_for_mobile=is_mobile_request
                )
                
                # Obtener título y descripción individual
                title = request.POST.get(f'title_{idx}', uploaded_file.name.rsplit('.', 1)[0])
                description = request.POST.get(f'description_{idx}', '')
                
                # Validar archivo procesado
                if not processed_file.content_type.startswith('image/'):
                    errors.append(f'{uploaded_file.name}: No es una imagen válida')
                    continue
                
                if processed_file.size > 10 * 1024 * 1024:  # 10MB
                    errors.append(f'{uploaded_file.name}: Archivo demasiado grande (máx 10MB)')
                    continue
                
                # Crear imagen
                image = Image(
                    image=processed_file,
                    title=title,
                    description=description,
                    tags=shared_tags,
                    original_format=original_ext.lstrip('.'),
                    was_converted=was_converted,
                    **shared_data
                )
                
                if was_converted:
                    logger.info(f"Imagen {uploaded_file.name} convertida de {original_ext} a JPEG")
                
                # Si el usuario es superuser, aprobar directamente sin pasar por Vision API
                if request.user.is_superuser:
                    image.status = 'approved'
                    image.moderated_by = request.user
                    image.moderation_date = timezone.now()
                    image.moderation_notes = 'Aprobada automáticamente por superusuario'
                    image.vision_api_checked = False
                    image.vision_api_safe = True
                    image.vision_api_details = {'skipped': 'Superuser approval - bypassed Vision API'}
                    logger.info(f"Imagen aprobada automáticamente para superusuario {request.user.username}")
                # Procesar con Google Vision API si está habilitado (solo si no es móvil para mejor rendimiento)
                elif (getattr(settings, 'GOOGLE_VISION_ENABLED', False) and 
                    not is_mobile_request and 
                    len(uploaded_files) <= 5):  # Limitar Vision API en carga múltiple
                    try:
                        vision_result = check_image_with_vision_api(image.image, extract_labels=True, extract_text=True)
                        
                        image.vision_api_checked = True
                        image.vision_api_safe = vision_result.get('safe', False)
                        image.vision_api_details = vision_result
                        
                        # Procesar etiquetas automáticas
                        detected_labels = vision_result.get('labels', [])
                        detected_text = vision_result.get('text', '')
                        
                        if detected_labels or detected_text:
                            auto_tags = process_vision_tags_for_volleyball(detected_labels, detected_text)
                            image.auto_tags = auto_tags
                        
                        # Auto-aprobar si es segura
                        if (vision_result.get('safe', False) and 
                            vision_result.get('details', {}).get('api_response_ok', False) and
                            getattr(settings, 'AUTO_MODERATION_ENABLED', False)):
                            image.status = 'approved'
                            image.moderated_by = request.user
                            image.moderation_date = timezone.now()
                            image.moderation_notes = 'Auto-aprobada por Google Vision API'
                            
                    except Exception as e:
                        logger.error(f"Error en Vision API para {uploaded_file.name}: {str(e)}")
                        image.vision_api_checked = False
                        image.vision_api_safe = False
                        image.vision_api_details = {'error': str(e), 'api_response_ok': False}
                else:
                    # En móvil o carga múltiple, saltar Vision API para mejor rendimiento
                    image.vision_api_checked = False
                    image.vision_api_safe = True  # Asumir seguro para no bloquear
                    image.vision_api_details = {'skipped': 'Mobile or bulk upload optimization'}
                
                # Guardar imagen
                image.save()
                
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
                errors.append(f'{uploaded_file.name}: {str(e)}')
        
        # Mensajes de resultado
        if success_count > 0:
            messages.success(request, f'✅ {success_count} imagen(es) subida(s) correctamente.')
        
        if errors:
            for error in errors[:5]:  # Mostrar máximo 5 errores
                messages.warning(request, error)
            if len(errors) > 5:
                messages.warning(request, f'... y {len(errors) - 5} error(es) más.')
        
        if success_count > 0:
            # Redirigir al álbum si se agregaron fotos a uno existente
            existing_album_id = request.POST.get('existing_album_id')
            if existing_album_id:
                messages.success(
                    request,
                    f'✅ {success_count} imagen(es) agregada(s) al álbum correctamente.'
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
                    'album_name': first_image.album_name or 'Álbum',
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
        'current_year': timezone.now().year,
        'selected_match': selected_match,
        'existing_album': existing_album,
    }

    return render(request, 'content/image_bulk_upload.html', context)


@tenant_access_required()
def image_detail(request, image_id):
    """Vista de detalle de imagen"""
    image = get_object_or_404(
        Image.objects.select_related(
            'match__home_team', 'match__away_team', 'match__league',
            'uploaded_by', 'moderated_by'
        ).prefetch_related('categories'),
        id=image_id
    )
    if image.organization != request.tenant and not request.user.is_superuser:
        raise Http404

    # Solo mostrar imágenes aprobadas a usuarios normales
    if not request.user.is_staff and image.status != 'approved':
        messages.error(request, 'Imagen no disponible.')
        return redirect('content:image_gallery')
    
    # Imágenes relacionadas del mismo partido
    related_images = Image.objects.filter(
        match=image.match,
        status='approved'
    ).exclude(id=image.id)[:6]
    
    context = {
        'image': image,
        'related_images': related_images,
    }
    
    return render(request, 'content/image_detail.html', context)


@tenant_access_required()
def match_images(request, match_id):
    """Vista de imágenes de un partido específico"""
    match = get_object_or_404(
        Match.objects.select_related('home_team', 'away_team', 'league'),
        id=match_id
    )
    
    images = Image.objects.filter(
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
        'total_images': images.count(),
    }

    return render(request, 'content/match_images.html', context)


@tenant_access_required()
def album_group_images(request, album_group_id):
    """Vista de imágenes de un álbum de grupo (sin partido)"""
    # album_group_id ya viene como UUID desde la URL (gracias al path converter <uuid:album_group_id>)
    images = Image.objects.filter(
        album_group_id=album_group_id,
        status='approved'
    ).select_related('uploaded_by').prefetch_related('categories').order_by('-upload_date')
    
    if not images.exists():
        raise Http404("Álbum no encontrado")
    
    # Obtener información del álbum desde la primera imagen
    first_image = images.first()
    
    # Paginación
    paginator = Paginator(images, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Preparar información del álbum
    album_info = {
        'album_group_id': album_group_id,
        'album_name': first_image.album_name or 'Álbum',
        'image_count': images.count(),
        'upload_date': first_image.upload_date,
        'categories': first_image.categories.all(),
        'image_type': first_image.get_image_type_display(),
    }
    
    context = {
        'album': album_info,
        'page_obj': page_obj,
        'all_images': images,
        'total_images': images.count(),
    }

    return render(request, 'content/album_group_images.html', context)


# ---------------------------------------------------------------------------
# Vistas de moderación de imágenes
# ---------------------------------------------------------------------------

def image_moderation(request):
    """Vista de moderación para admins"""
    images = Image.objects.select_related(
        'match__home_team', 'match__away_team', 'match__league',
        'uploaded_by'
    ).prefetch_related('categories').filter(status='pending').order_by('upload_date')
    
    # Paginación
    paginator = Paginator(images, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'pending_count': images.count(),
    }
    
    return render(request, 'content/image_moderation.html', context)


@tenant_access_required(staff=True)
def image_moderate_action(request, image_id):
    """Acción de moderación individual"""
    image = get_object_or_404(Image, id=image_id, status='pending')
    
    if request.method == 'POST':
        form = ImageModerationForm(request.POST, instance=image)
        if form.is_valid():
            action = form.cleaned_data['action']
            notes = form.cleaned_data['moderation_notes']
            
            image.moderate(
                moderator=request.user,
                approved=(action == 'approve'),
                notes=notes
            )
            
            action_text = 'aprobada' if action == 'approve' else 'rechazada'
            messages.success(request, f'Imagen {action_text} correctamente.')
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
    """Moderación masiva de imágenes"""
    if request.method == 'POST':
        action = request.POST.get('action')
        image_ids = request.POST.getlist('image_ids')
        notes = request.POST.get('notes', '')
        
        if action in ['approve', 'reject'] and image_ids:
            images = Image.objects.filter(id__in=image_ids, status='pending')
            approved = (action == 'approve')
            
            for image in images:
                image.moderate(
                    moderator=request.user,
                    approved=approved,
                    notes=notes
                )
            
            action_text = 'aprobadas' if approved else 'rechazadas'
            messages.success(request, f'{images.count()} imágenes {action_text}.')
        
        return redirect('content:image_moderation')
    
    return redirect('content:image_moderation')


@login_required
@user_passes_test(lambda u: u.is_superuser, login_url='/')
@require_POST
def moderate_image_api(request, image_id):
    """API para moderar una imagen vía AJAX"""
    try:
        image = Image.objects.get(id=image_id, status='pending')
        action = request.POST.get('action')  # 'approve' o 'reject'
        notes = request.POST.get('notes', '')
        
        if action not in ['approve', 'reject']:
            return JsonResponse({
                'success': False,
                'error': 'Acción no válida'
            }, status=400)
        
        # Usar el método existente de moderación
        approved = (action == 'approve')
        image.moderate(
            moderator=request.user,
            approved=approved,
            notes=notes
        )
        
        action_text = 'aprobada' if approved else 'rechazada'
        
        return JsonResponse({
            'success': True,
            'message': f'Imagen "{image.title}" {action_text} correctamente',
            'image_title': image.title,
            'action': action
        })
        
    except Image.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Imagen no encontrada o ya moderada'
        }, status=404)
    except Exception as e:
        logger.error(f"Error moderando imagen {image_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Error interno del servidor'
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
