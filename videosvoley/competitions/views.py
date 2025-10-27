from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
import logging

from .models import League, Match, Standing, ScrapingEndpoint

logger = logging.getLogger(__name__)


def league_list(request):
    """Lista de ligas con filtros"""
    leagues = League.objects.select_related('category').prefetch_related('matches').all()
    
    # Filtros
    competition_type = request.GET.get('competition_type')
    visibility_type = request.GET.get('visibility_type')
    search_query = request.GET.get('search', '').strip()
    show_all = request.GET.get('show_all', '0') == '1'
    
    # Filtrar por ligas principales si no se especifica otra cosa
    if not visibility_type and not show_all:
        leagues = leagues.visible_in_app()
    
    # Aplicar filtros
    if competition_type:
        leagues = leagues.filter(competition_type=competition_type)
    
    if visibility_type:
        leagues = leagues.filter(visibility_type=visibility_type)
    
    if search_query:
        leagues = leagues.filter(
            Q(name__icontains=search_query) |
            Q(season__icontains=search_query) |
            Q(federation_id__icontains=search_query)
        )
    
    # Paginación
    paginator = Paginator(leagues, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'competition_types': League.COMPETITION_TYPES,
        'visibility_types': League.VISIBILITY_TYPES,
        'selected_competition_type': competition_type,
        'selected_visibility_type': visibility_type,
        'search_query': search_query,
        'show_all': show_all,
    }
    
    return render(request, 'competitions/league_list.html', context)


def league_detail(request, league_id):
    """Detalle de una liga con partidos y clasificación"""
    league = get_object_or_404(League, id=league_id)
    
    # Obtener partidos de la liga
    matches = league.matches.all().order_by('-match_date')
    
    # Obtener clasificación
    standings = league.standings.all().order_by('position')
    
    # Obtener endpoints de scraping
    endpoints = league.endpoints.filter(is_active=True)
    
    context = {
        'league': league,
        'matches': matches,
        'standings': standings,
        'endpoints': endpoints,
    }
    
    return render(request, 'competitions/league_detail.html', context)


def match_detail(request, match_id):
    """Detalle de un partido"""
    match = get_object_or_404(Match, id=match_id)
    
    # Obtener partidos relacionados (misma liga, fechas cercanas)
    related_matches = []
    if match.league:
        related_matches = match.league.matches.exclude(id=match.id).order_by('-match_date')[:5]
    
    context = {
        'match': match,
        'related_matches': related_matches,
    }
    
    return render(request, 'competitions/match_detail.html', context)


def match_calendar(request):
    """Calendario de partidos"""
    matches = Match.objects.select_related('league', 'home_team', 'away_team').all()
    
    # Filtros
    league_filter = request.GET.get('league')
    status_filter = request.GET.get('status')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    # Aplicar filtros
    if league_filter:
        matches = matches.filter(league_id=league_filter)
    
    if status_filter:
        matches = matches.filter(status=status_filter)
    
    if date_from:
        try:
            date_from_obj = timezone.datetime.strptime(date_from, '%Y-%m-%d').date()
            matches = matches.filter(match_date__date__gte=date_from_obj)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_obj = timezone.datetime.strptime(date_to, '%Y-%m-%d').date()
            matches = matches.filter(match_date__date__lte=date_to_obj)
        except ValueError:
            pass
    
    # Ordenar por fecha
    matches = matches.order_by('match_date')
    
    # Paginación
    paginator = Paginator(matches, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Obtener ligas para filtro
    leagues = League.objects.filter(is_active=True).order_by('name')
    
    context = {
        'page_obj': page_obj,
        'leagues': leagues,
        'match_statuses': Match.MATCH_STATES,
        'selected_league': league_filter,
        'selected_status': status_filter,
        'date_from': date_from,
        'date_to': date_to,
    }
    
    return render(request, 'competitions/match_calendar.html', context)


def standings(request, league_id):
    """Clasificación de una liga"""
    league = get_object_or_404(League, id=league_id)
    standings_list = league.standings.all().order_by('position')
    
    context = {
        'league': league,
        'standings': standings_list,
    }
    
    return render(request, 'competitions/standings.html', context)


@login_required
def friendly_match_create(request):
    """Crear partido amistoso"""
    if request.method == 'POST':
        # Aquí irá la lógica de creación
        # Por ahora solo un placeholder
        messages.success(request, 'Funcionalidad de creación de partidos amistosos en desarrollo')
        return redirect('competitions:match_calendar')
    
    context = {
        'leagues': League.objects.filter(is_active=True),
    }
    
    return render(request, 'competitions/friendly_match_create.html', context)