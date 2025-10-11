from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.contrib.postgres.search import TrigramSimilarity
from django.http import JsonResponse
from django.conf import settings
from django.views.decorators.http import require_POST
from unidecode import unidecode
from datetime import datetime, timedelta
import calendar
from django.utils import timezone
import logging
from .models import Video, Comment, Category, League, Match, Team, Standing, Image
from .forms import VideoForm, CommentForm, ImageUploadForm, ImageFilterForm, ImageModerationForm, FriendlyMatchForm

# Configurar logger
logger = logging.getLogger(__name__)


def user_is_approved(user):
    """Verifica si el usuario está aprobado para acceder al contenido"""
    return user.is_approved


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def video_list(request):
    videos = Video.objects.select_related('category', 'created_by', 'match__home_team', 'match__away_team', 'match__league').prefetch_related('comments').all()
    categories = Category.objects.filter(is_active=True)
    leagues = League.objects.filter(is_active=True)
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
            return redirect('videos:video_list')
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


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def league_list(request):
    """Vista para mostrar todas las ligas disponibles"""
    leagues = League.objects.filter(is_active=True).prefetch_related('matches__videos')
    categories = Category.objects.filter(is_active=True).order_by('name')
    
    # Variable para controlar si mostrar todo el contenido
    show_all = request.GET.get('show_all', '0') == '1'
    category_filter = request.GET.get('category')
    
    # Aplicar filtro de categoría específica
    if category_filter:
        leagues = leagues.filter(category_id=category_filter)
    # Filtrar por categorías preferidas del usuario si no se especifica otra cosa
    elif not show_all and request.user.preferred_categories.exists():
        user_categories = request.user.preferred_categories.all()
        leagues = leagues.filter(category__in=user_categories)
    
    return render(request, 'videos/league_list.html', {
        'leagues': leagues,
        'categories': categories,
        'selected_category': category_filter,
        'show_all': show_all,
        'has_preferences': request.user.preferred_categories.exists(),
    })


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def league_detail(request, league_id):
    """Vista detallada de una liga con partidos y clasificación"""
    league = get_object_or_404(League, id=league_id, is_active=True)
    
    # Obtener partidos de la liga
    matches = Match.objects.filter(league=league).select_related(
        'home_team', 'away_team'
    ).prefetch_related('videos').order_by('-match_date')
    
    # Obtener clasificación
    standings = league.standings.select_related('team').order_by('position')
    
    # Filtros opcionales
    round_filter = request.GET.get('round')
    if round_filter:
        matches = matches.filter(round_number=round_filter)
    
    # Obtener jornadas disponibles
    available_rounds = matches.values_list('round_number', flat=True).distinct().order_by('round_number')
    
    # Paginación de partidos
    paginator = Paginator(matches, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'videos/league_detail.html', {
        'league': league,
        'page_obj': page_obj,
        'standings': standings,
        'available_rounds': available_rounds,
        'selected_round': round_filter
    })


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def match_detail(request, match_id):
    """Vista detallada de un partido con sus videos"""
    match = get_object_or_404(
        Match.objects.select_related('home_team', 'away_team', 'league'), 
        id=match_id
    )
    
    # Obtener videos del partido
    videos = match.videos.select_related('created_by', 'category').all()
    
    return render(request, 'videos/match_detail.html', {
        'match': match,
        'videos': videos
    })


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def calendar_view(request):
    """Vista del calendario de partidos"""
    # Configuración del club
    CLUB_TEAM_NAME = 'SANT JOSEP'
    
    # Obtener filtros
    show_all_teams = request.GET.get('all_teams', '0') == '1'
    show_all = request.GET.get('show_all', '0') == '1'
    league_filter = request.GET.get('league')
    category_filter = request.GET.get('category')
    
    # Consulta base de partidos
    matches = Match.objects.select_related(
        'home_team', 'away_team', 'league', 'league__category'
    ).order_by('match_date')
    
    # Filtrar por equipo del club por defecto
    if not show_all_teams:
        matches = matches.filter(
            Q(home_team__name__icontains=CLUB_TEAM_NAME) | 
            Q(away_team__name__icontains=CLUB_TEAM_NAME) |
            Q(home_team_text__icontains=CLUB_TEAM_NAME) |
            Q(away_team_text__icontains=CLUB_TEAM_NAME)
        )
    
    # Aplicar filtro de liga
    if league_filter:
        matches = matches.filter(league_id=league_filter)
    
    # Aplicar filtro de categoría
    if category_filter:
        matches = matches.filter(league__category_id=category_filter)
    # Si no hay filtro de categoría, aplicar preferencias del usuario
    elif not show_all and request.user.preferred_categories.exists():
        user_categories = request.user.preferred_categories.all()
        matches = matches.filter(league__category__in=user_categories)
    
    # Obtener datos para filtros
    leagues = League.objects.filter(is_active=True).order_by('name')
    categories = Category.objects.filter(is_active=True).order_by('name')
    
    # Obtener el mes actual o el solicitado
    year = int(request.GET.get('year', timezone.now().year))
    month = int(request.GET.get('month', timezone.now().month))
    
    # Filtrar partidos del mes seleccionado
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = datetime(year, month + 1, 1) - timedelta(days=1)
    
    monthly_matches = matches.filter(
        match_date__date__gte=start_date.date(),
        match_date__date__lte=end_date.date()
    )
    
    # Navegación de meses
    prev_month = start_date - timedelta(days=1)
    next_month = end_date + timedelta(days=1)
    
    # Generar grid del calendario
    cal = calendar.Calendar(firstweekday=0)  # Lunes como primer día
    month_days = cal.monthdayscalendar(year, month)
    
    # Crear diccionario de partidos por día
    matches_by_day = {}
    for match in monthly_matches:
        day = match.match_date.day
        if day not in matches_by_day:
            matches_by_day[day] = []
        matches_by_day[day].append(match)
    
    # Crear estructura del calendario con partidos
    calendar_weeks = []
    for week in month_days:
        calendar_week = []
        for day in week:
            if day == 0:
                calendar_week.append({
                    'day': None,
                    'is_current_month': False,
                    'matches': []
                })
            else:
                day_matches = matches_by_day.get(day, [])
                is_today = (datetime.now().date() == datetime(year, month, day).date())
                calendar_week.append({
                    'day': day,
                    'is_current_month': True,
                    'is_today': is_today,
                    'matches': day_matches,
                    'match_count': len(day_matches)
                })
        calendar_weeks.append(calendar_week)
    
    # Obtener modo de vista (lista o calendario)
    view_mode = request.GET.get('view', 'list')  # 'list' o 'calendar'
    
    # Nombres de meses en español
    month_names_es = {
        1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
        5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
        9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
    }
    
    return render(request, 'videos/calendar.html', {
        'matches': monthly_matches,
        'leagues': leagues,
        'categories': categories,
        'selected_league': league_filter,
        'selected_category': category_filter,
        'show_all_teams': show_all_teams,
        'show_all': show_all,
        'club_team_name': CLUB_TEAM_NAME,
        'current_month': start_date,
        'prev_month': prev_month,
        'next_month': next_month,
        'year': year,
        'month': month,
        'calendar_weeks': calendar_weeks,
        'view_mode': view_mode,
        'month_name': month_names_es[month],
        'has_preferences': request.user.preferred_categories.exists(),
    })


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
@user_passes_test(lambda u: u.is_staff or u.groups.filter(name='VideoManagers').exists(), login_url='/')
def friendly_match_create(request):
    """Vista para crear un partido amistoso"""
    if request.method == 'POST':
        # Debug: ver qué datos estamos recibiendo
        logger.debug(f"POST data received: {request.POST}")
        
        form = FriendlyMatchForm(request.POST)
        if form.is_valid():
            match = form.save()
            messages.success(
                request, 
                f'Partido amistoso creado: {match.home_team_display} vs {match.away_team_display}'
            )
            return redirect('videos:calendar_view')
        else:
            # Mostrar errores con más detalle
            logger.error(f"Form errors: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    if field == '__all__':
                        messages.error(request, f'{error}')
                    else:
                        messages.error(request, f'{field}: {error}')
    else:
        form = FriendlyMatchForm()
    
    return render(request, 'videos/friendly_match_form.html', {
        'form': form,
    })


@login_required
def ajax_search_teams(request):
    """Vista AJAX para buscar equipos con autocompletado inteligente"""
    from django.http import JsonResponse
    
    query = request.GET.get('q', '').strip()
    category_id = request.GET.get('category_id', '').strip()
    
    if len(query) < 2:
        return JsonResponse({'teams': []})
    
    # Buscar equipos existentes
    teams_query = Team.objects.filter(name__icontains=query)
    
    # Filtrar por categoría si se especifica
    if category_id:
        try:
            category = Category.objects.get(id=category_id)
            teams_query = teams_query.filter(category=category)
        except Category.DoesNotExist:
            pass
    
    # Limitar a 10 resultados
    teams = teams_query.order_by('name')[:10]
    
    # Formatear respuesta
    teams_data = []
    for team in teams:
        display_name = team.name
        if team.category:
            display_name += f" ({team.category.name})"
        if team.club:
            display_name += f" - {team.club.official_name}"
        
        teams_data.append({
            'id': team.id,
            'name': team.name,
            'display': display_name,
            'category': team.category.name if team.category else None,
        })
    
    return JsonResponse({'teams': teams_data})


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def standings_view(request):
    """Vista de clasificación de las ligas"""
    # Obtener filtros
    league_filter = request.GET.get('league')
    category_filter = request.GET.get('category')
    show_all = request.GET.get('show_all', '0') == '1'
    
    # Configuración del club
    CLUB_TEAM_NAME = 'SANT JOSEP'
    
    # Consulta base de clasificaciones
    standings = Standing.objects.select_related(
        'team', 'league', 'league__category'
    ).order_by('league__name', 'position')
    
    # Aplicar filtro de liga
    if league_filter:
        standings = standings.filter(league_id=league_filter)
    
    # Aplicar filtro de categoría
    if category_filter:
        standings = standings.filter(league__category_id=category_filter)
    # Si no hay filtro de categoría, aplicar preferencias del usuario
    elif not show_all and request.user.preferred_categories.exists():
        user_categories = request.user.preferred_categories.all()
        standings = standings.filter(league__category__in=user_categories)
    
    # Agrupar por liga
    standings_by_league = {}
    for standing in standings:
        league_name = standing.league.name
        if league_name not in standings_by_league:
            standings_by_league[league_name] = {
                'league': standing.league,
                'standings': []
            }
        standings_by_league[league_name]['standings'].append(standing)
    
    # Obtener datos para filtros
    leagues = League.objects.filter(is_active=True).order_by('name')
    categories = Category.objects.filter(is_active=True).order_by('name')
    
    return render(request, 'videos/standings.html', {
        'standings_by_league': standings_by_league,
        'leagues': leagues,
        'categories': categories,
        'selected_league': league_filter,
        'selected_category': category_filter,
        'club_team_name': CLUB_TEAM_NAME,
        'show_all': show_all,
        'has_preferences': request.user.preferred_categories.exists(),
    })


@login_required
def ajax_matches_by_category(request):
    """Vista AJAX para obtener partidos filtrados por categoría"""
    category_id = request.GET.get('category_id')
    club_team_name = getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')
    
    # Construir query base para equipos del club
    club_query = (
        Q(home_team__name__icontains=club_team_name) | 
        Q(away_team__name__icontains=club_team_name) |
        Q(home_team_text__icontains=club_team_name) |
        Q(away_team_text__icontains=club_team_name)
    )
    
    # Si hay categoría específica, filtrar por equipos de esa categoría
    if category_id and category_id != '':
        try:
            category = Category.objects.get(id=category_id)
            # Filtrar por equipos que tengan la categoría específica O por liga de esa categoría
            category_query = (Q(home_team__category=category) | Q(away_team__category=category) |
                            Q(league__category=category))
            
            # Combinar: partidos del club Y de la categoría específica
            final_query = club_query & category_query
        except Category.DoesNotExist:
            final_query = club_query
    else:
        # Sin categoría específica, mostrar todos los partidos del club
        final_query = club_query
    
    # Obtener partidos
    matches = Match.objects.select_related(
        'home_team', 'away_team', 'home_team__category', 'away_team__category', 
        'league', 'league__category'
    ).filter(final_query).order_by('-match_date')[:50]  # Limitar a 50 partidos más recientes
    
    # Formatear respuesta
    matches_data = []
    for match in matches:
        matches_data.append({
            'id': match.id,
            'text': f"{match.home_team.name} vs {match.away_team.name} - {match.match_date.strftime('%d/%m/%Y')} ({match.league.name})"
        })
    
    return JsonResponse({
        'matches': matches_data
    })


@login_required
def ajax_teams_by_league_category(request):
    """Vista AJAX para obtener equipos filtrados por categoría de liga (para admin)"""
    league_id = request.GET.get('league_id')
    filter_by_category = request.GET.get('filter_by_category', 'true').lower() == 'true'
    
    if league_id and filter_by_category:
        try:
            from .models import League
            league = League.objects.get(id=league_id)
            
            if league.category:
                # Filtrar equipos por la categoría de la liga
                teams = Team.objects.filter(category=league.category).order_by('name')
            else:
                # Si la liga no tiene categoría, mostrar todos
                teams = Team.objects.all().order_by('name')
        except League.DoesNotExist:
            teams = Team.objects.all().order_by('name')
    else:
        # Sin filtrado o sin liga, mostrar todos los equipos
        teams = Team.objects.all().order_by('name')
    
    # Formatear respuesta
    teams_data = []
    for team in teams:
        display_name = team.name
        if team.category:
            display_name += f" ({team.category.name})"
        
        teams_data.append({
            'id': team.id,
            'text': display_name
        })
    
    return JsonResponse({
        'teams': teams_data
    })


# ===============================
# VISTAS DE GESTIÓN DE IMÁGENES
# ===============================

@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def image_gallery(request):
    """Vista de galería de imágenes con filtros"""
    images = Image.objects.select_related(
        'match__home_team', 'match__away_team', 'match__league', 
        'uploaded_by'
    ).prefetch_related('categories').filter(status='approved').order_by('-upload_date')
    
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
        from collections import Counter
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
    }
    
    return render(request, 'videos/image_gallery.html', context)


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def image_upload(request):
    """Vista para subir imágenes"""
    if request.method == 'POST':
        form = ImageUploadForm(request.POST, request.FILES)
        if form.is_valid():
            image = form.save(commit=False)
            image.uploaded_by = request.user
            
            # Procesar imagen (convertir HEIC si es necesario)
            try:
                from .utils import process_uploaded_image
                
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
                club_query = (
                    Q(home_team__name__icontains=getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')) |
                    Q(away_team__name__icontains=getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')) |
                    Q(home_team_text__icontains=getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')) |
                    Q(away_team_text__icontains=getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP'))
                )
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
                
                return render(request, 'videos/image_upload.html', {
                    'form': form,
                    'recent_matches': recent_matches
                })
            
            # Procesar con Google Vision API si está habilitado
            if getattr(settings, 'GOOGLE_VISION_ENABLED', False):
                try:
                    from .utils import check_image_with_vision_api, process_vision_tags_for_volleyball
                    
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
            
            # Mensaje dinámico según el estado de la imagen
            if image.status == 'approved':
                auto_tags_msg = f" Se detectaron automáticamente las etiquetas: {', '.join(image.auto_tags[:3])}." if image.auto_tags else ""
                messages.success(request, f'Imagen subida y aprobada automáticamente.{auto_tags_msg}')
            else:
                auto_tags_msg = f" Se detectaron automáticamente las etiquetas: {', '.join(image.auto_tags[:3])}." if image.auto_tags else ""
                messages.success(request, f'Imagen subida correctamente. Está pendiente de moderación.{auto_tags_msg}')
            
            return redirect('videos:image_gallery')
        else:
            # El formulario no es válido, mostrar errores
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = ImageUploadForm()
    
    # Obtener partidos recientes para sugerir (solo pasados + el próximo)
    club_query = (
        Q(home_team__name__icontains=getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')) |
        Q(away_team__name__icontains=getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')) |
        Q(home_team_text__icontains=getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')) |
        Q(away_team_text__icontains=getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP'))
    )
    
    now = timezone.now()
    
    # Partidos del pasado (últimos 10)
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
    
    return render(request, 'videos/image_upload.html', context)


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def image_bulk_upload(request):
    """Vista para subir múltiples imágenes a la vez"""
    if request.method == 'POST':
        uploaded_files = request.FILES.getlist('images')
        
        if not uploaded_files:
            messages.error(request, 'No se seleccionaron imágenes.')
            return redirect('videos:image_bulk_upload')
        
        # Datos compartidos para todas las imágenes
        shared_data = {
            'uploaded_by': request.user,
            'image_type': request.POST.get('image_type', 'other'),
            'year': request.POST.get('year', timezone.now().year),
        }
        
        # Match y categorías opcionales compartidos
        match_id = request.POST.get('match')
        if match_id:
            try:
                shared_data['match'] = Match.objects.get(id=match_id)
            except Match.DoesNotExist:
                pass
        
        # Etiquetas compartidas
        shared_tags = request.POST.get('tags', '').strip()
        
        # Procesar cada imagen
        success_count = 0
        errors = []
        
        for idx, uploaded_file in enumerate(uploaded_files):
            try:
                # Procesar imagen (convertir HEIC si es necesario)
                from .utils import process_uploaded_image
                
                processed_file, original_ext, was_converted = process_uploaded_image(uploaded_file)
                
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
                
                # Procesar con Google Vision API si está habilitado
                if getattr(settings, 'GOOGLE_VISION_ENABLED', False):
                    try:
                        from .utils import check_image_with_vision_api, process_vision_tags_for_volleyball
                        
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
                    if match.league and match.league.category:
                        categories_to_add.append(match.league.category)
                
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
            return redirect('videos:image_gallery')
        else:
            return redirect('videos:image_bulk_upload')
    
    # GET request
    # Obtener partidos recientes para sugerir (solo pasados + el próximo)
    club_query = (
        Q(home_team__name__icontains=getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')) |
        Q(away_team__name__icontains=getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')) |
        Q(home_team_text__icontains=getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP')) |
        Q(away_team_text__icontains=getattr(settings, 'CLUB_TEAM_NAME', 'SANT JOSEP'))
    )
    
    now = timezone.now()
    
    # Partidos del pasado (últimos 10)
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
    }
    
    return render(request, 'videos/image_bulk_upload.html', context)


@login_required
@user_passes_test(user_is_approved, login_url='/pending-approval/')
def image_detail(request, image_id):
    """Vista de detalle de imagen"""
    image = get_object_or_404(
        Image.objects.select_related(
            'match__home_team', 'match__away_team', 'match__league',
            'uploaded_by', 'moderated_by'
        ).prefetch_related('categories'),
        id=image_id
    )
    
    # Solo mostrar imágenes aprobadas a usuarios normales
    if not request.user.is_staff and image.status != 'approved':
        messages.error(request, 'Imagen no disponible.')
        return redirect('videos:image_gallery')
    
    # Imágenes relacionadas del mismo partido
    related_images = Image.objects.filter(
        match=image.match,
        status='approved'
    ).exclude(id=image.id)[:6]
    
    context = {
        'image': image,
        'related_images': related_images,
    }
    
    return render(request, 'videos/image_detail.html', context)


@login_required
@user_passes_test(lambda u: u.is_staff, login_url='/')
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
    
    return render(request, 'videos/image_moderation.html', context)


@login_required
@user_passes_test(lambda u: u.is_staff, login_url='/')
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
            return redirect('videos:image_moderation')
    else:
        form = ImageModerationForm()
    
    context = {
        'image': image,
        'form': form,
    }
    
    return render(request, 'videos/image_moderate.html', context)


@login_required
@user_passes_test(lambda u: u.is_staff, login_url='/')
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
        
        return redirect('videos:image_moderation')
    
    return redirect('videos:image_moderation')


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
        'total_images': images.count(),
    }
    
    return render(request, 'videos/match_images.html', context)


def about(request):
    """Vista de la página Quiénes somos"""
    return render(request, 'videos/about.html')


# ===============================
# VISTAS DE NOTIFICACIONES Y MODERACIÓN
# ===============================

@login_required
@user_passes_test(lambda u: u.is_superuser, login_url='/')
def moderation_counts_api(request):
    """API para obtener contadores de elementos pendientes de moderación"""
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    
    # Contar usuarios pendientes de aprobación
    pending_users_count = User.objects.filter(is_approved=False).count()
    
    # Contar imágenes pendientes de moderación
    pending_images_count = Image.objects.filter(status='pending').count()
    
    # Total de elementos pendientes
    total_pending = pending_users_count + pending_images_count
    
    return JsonResponse({
        'success': True,
        'pending_users': pending_users_count,
        'pending_images': pending_images_count,
        'total_pending': total_pending
    })


@login_required
@user_passes_test(lambda u: u.is_superuser, login_url='/')
def moderation_panel(request):
    """Panel de moderación simplificado para superusers"""
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    
    # Obtener usuarios pendientes de aprobación
    pending_users = User.objects.filter(is_approved=False).order_by('date_joined')
    
    # Obtener imágenes pendientes de moderación
    pending_images = Image.objects.filter(status='pending').select_related(
        'uploaded_by', 'match__home_team', 'match__away_team', 'match__league'
    ).prefetch_related('categories').order_by('upload_date')
    
    context = {
        'pending_users': pending_users,
        'pending_images': pending_images,
        'pending_users_count': pending_users.count(),
        'pending_images_count': pending_images.count(),
    }
    
    return render(request, 'videos/moderation_panel.html', context)


@login_required
@user_passes_test(lambda u: u.is_superuser, login_url='/')
@require_POST
def approve_user_api(request, user_id):
    """API para aprobar un usuario vía AJAX"""
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    
    try:
        user = User.objects.get(id=user_id, is_approved=False)
        user.is_approved = True
        user.is_active = True  # Asegurarse de que el usuario esté activo al aprobar
        user.save(update_fields=['is_approved', 'is_active'])
        
        # Enviar email de confirmación si está configurado
        if getattr(settings, 'NOTIFICATION_EMAIL_ENABLED', False):
            try:
                from videosvoley.core.email_utils import send_notification_email
                send_notification_email(
                    subject=f'Usuario aprobado - {user.username}',
                    template_name='emails/user_approved.html',
                    context={'user': user},
                    recipient_list=[user.email] if user.email else []
                )
            except Exception as e:
                logger.warning(f"Error enviando email de aprobación: {e}")
        
        return JsonResponse({
            'success': True,
            'message': f'Usuario {user.username} aprobado correctamente',
            'user_name': user.username
        })
        
    except User.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Usuario no encontrado o ya aprobado'
        }, status=404)
    except Exception as e:
        logger.error(f"Error aprobando usuario {user_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Error interno del servidor'
        }, status=500)


@login_required
@user_passes_test(lambda u: u.is_superuser, login_url='/')
@require_POST
def reject_user_api(request, user_id):
    """API para rechazar un usuario vía AJAX"""
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    
    try:
        user = User.objects.get(id=user_id, is_approved=False)
        # Rechazar = desactivar el usuario y mantener is_approved en False
        user.is_active = False
        user.save(update_fields=['is_active'])
        
        # Enviar email de rechazo si está configurado
        if getattr(settings, 'NOTIFICATION_EMAIL_ENABLED', False):
            try:
                from videosvoley.core.email_utils import send_notification_email
                send_notification_email(
                    subject=f'Actualización de tu solicitud en I Love Voley',
                    template_name='emails/user_rejected.html',
                    context={
                        'user': user,
                        'site_name': 'I Love Voley',
                    },
                    recipient_list=[user.email] if user.email else []
                )
            except Exception as e:
                logger.warning(f"Error enviando email de rechazo: {e}")
        
        return JsonResponse({
            'success': True,
            'message': f'Usuario {user.username} rechazado correctamente',
            'user_name': user.username
        })
        
    except User.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Usuario no encontrado o ya procesado'
        }, status=404)
    except Exception as e:
        logger.error(f"Error rechazando usuario {user_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': 'Error interno del servidor'
        }, status=500)


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
