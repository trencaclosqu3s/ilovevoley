from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
import logging

from .models import Video, Comment, Image, Category

logger = logging.getLogger(__name__)


def video_list(request):
    """Lista de videos con filtros"""
    videos = Video.objects.select_related('category', 'created_by', 'match__home_team', 'match__away_team', 'match__league').prefetch_related('comments').all()
    categories = Category.objects.filter(is_active=True)
    
    # Filtros
    category_filter = request.GET.get('category')
    search_query = request.GET.get('search', '').strip()
    show_all = request.GET.get('show_all', '0') == '1'
    
    # Filtrar por categorías preferidas del usuario si no se especifica otra cosa
    if not category_filter and not show_all and request.user.is_authenticated and request.user.preferred_categories.exists():
        user_categories = request.user.preferred_categories.all()
        videos = videos.filter(category__in=user_categories)
    
    # Aplicar filtro de categoría
    if category_filter:
        videos = videos.filter(category_id=category_filter)
    
    # Aplicar búsqueda de texto
    if search_query:
        videos = videos.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(match__home_team__name__icontains=search_query) |
            Q(match__away_team__name__icontains=search_query) |
            Q(match__home_team_text__icontains=search_query) |
            Q(match__away_team_text__icontains=search_query)
        )
    
    # Paginación
    paginator = Paginator(videos, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'categories': categories,
        'selected_category': category_filter,
        'search_query': search_query,
        'show_all': show_all,
    }
    
    return render(request, 'content/video_list.html', context)


def video_detail(request, video_id):
    """Detalle de un video con comentarios"""
    video = get_object_or_404(Video, id=video_id)
    comments = video.comments.select_related('user').all()
    
    context = {
        'video': video,
        'comments': comments,
    }
    
    return render(request, 'content/video_detail.html', context)


def image_gallery(request):
    """Galería de imágenes con filtros"""
    images = Image.objects.select_related('uploaded_by', 'match').prefetch_related('categories').filter(status='approved')
    categories = Category.objects.filter(is_active=True)
    
    # Filtros
    category_filter = request.GET.get('category')
    image_type_filter = request.GET.get('image_type')
    year_filter = request.GET.get('year')
    search_query = request.GET.get('search', '').strip()
    
    # Aplicar filtros
    if category_filter:
        images = images.filter(categories__id=category_filter)
    
    if image_type_filter:
        images = images.filter(image_type=image_type_filter)
    
    if year_filter:
        images = images.filter(year=year_filter)
    
    if search_query:
        images = images.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(tags__icontains=search_query)
        )
    
    # Paginación
    paginator = Paginator(images, 24)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Años disponibles para filtro
    years = Image.objects.values_list('year', flat=True).distinct().order_by('-year')
    
    context = {
        'page_obj': page_obj,
        'categories': categories,
        'years': years,
        'image_types': Image.IMAGE_TYPES,
        'selected_category': category_filter,
        'selected_image_type': image_type_filter,
        'selected_year': year_filter,
        'search_query': search_query,
    }
    
    return render(request, 'content/image_gallery.html', context)


def image_detail(request, image_id):
    """Detalle de una imagen"""
    image = get_object_or_404(Image, id=image_id)
    
    context = {
        'image': image,
    }
    
    return render(request, 'content/image_detail.html', context)


@login_required
def image_upload(request):
    """Subida de imágenes"""
    if request.method == 'POST':
        # Aquí irá la lógica de subida
        # Por ahora solo un placeholder
        messages.success(request, 'Funcionalidad de subida en desarrollo')
        return redirect('content:image_gallery')
    
    context = {
        'image_types': Image.IMAGE_TYPES,
    }
    
    return render(request, 'content/image_upload.html', context)