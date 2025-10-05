from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.contrib.postgres.search import TrigramSimilarity
from unidecode import unidecode
from .models import Video, Comment, Category
from .forms import VideoForm, CommentForm


def user_is_approved(user):
    """Verifica si el usuario está aprobado para acceder al contenido"""
    return user.is_approved


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def video_list(request):
    videos = Video.objects.select_related('category', 'created_by').prefetch_related('comments').all()
    categories = Category.objects.filter(is_active=True)
    
    # Filtros
    category_filter = request.GET.get('category')
    search_query = request.GET.get('search', '').strip()
    
    # Aplicar filtro de categoría
    if category_filter:
        videos = videos.filter(category_id=category_filter)
    
    # Aplicar búsqueda de texto (case-insensitive, accent-insensitive)
    if search_query:
        # Buscar en título y descripción sin considerar acentos ni mayúsculas
        videos = videos.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    # Paginación
    paginator = Paginator(videos, 12)  # 12 videos por página
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    can_add = request.user.groups.filter(name='VideoManagers').exists()
    
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
    
    return render(request, 'videos/video_list.html', {
        'page_obj': page_obj,
        'categories': categories,
        'selected_category': category_filter,
        'search_query': search_query,
        'can_add': can_add
    })


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
@user_passes_test(lambda u: u.groups.filter(name='VideoManagers').exists())
def video_create(request):
    if request.method == 'POST':
        form = VideoForm(request.POST)
        if form.is_valid():
            video = form.save(commit=False)
            video.created_by = request.user
            video.save()
            messages.success(request, 'Vídeo añadido correctamente')
            return redirect('video_list')
    else:
        form = VideoForm()

    return render(request, 'videos/video_form.html', {'form': form})


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def video_detail(request, video_id):
    video = get_object_or_404(Video, id=video_id)
    
    # Manejar envío de comentarios
    if request.method == 'POST':
        comment_form = CommentForm(request.POST)
        if comment_form.is_valid():
            comment = comment_form.save(commit=False)
            comment.video = video
            comment.user = request.user
            comment.save()
            messages.success(request, '¡Comentario añadido correctamente!')
            return redirect('video_detail', video_id=video.id)
    else:
        comment_form = CommentForm()
    
    # Cargar comentarios con información del usuario
    comments = video.comments.select_related('user').all()
    
    return render(request, 'videos/video_detail.html', {
        'video': video,
        'comments': comments,
        'comment_form': comment_form
    })
