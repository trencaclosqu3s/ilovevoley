from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
import logging

from .models import Club, Team, ClubManager, TeamManager

logger = logging.getLogger(__name__)


def club_list(request):
    """Lista de clubs con filtros"""
    clubs = Club.objects.prefetch_related('teams').all()
    
    # Filtros
    province = request.GET.get('province')
    search_query = request.GET.get('search', '').strip()
    has_teams = request.GET.get('has_teams', '0') == '1'
    has_active_teams = request.GET.get('has_active_teams', '0') == '1'
    
    # Aplicar filtros
    if province:
        clubs = clubs.filter(province__icontains=province)
    
    if search_query:
        clubs = clubs.filter(
            Q(official_name__icontains=search_query) |
            Q(federation_id__icontains=search_query) |
            Q(president__icontains=search_query) |
            Q(email__icontains=search_query)
        )
    
    if has_teams:
        clubs = clubs.with_teams()
    
    if has_active_teams:
        clubs = clubs.with_active_teams()
    
    # Paginación
    paginator = Paginator(clubs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Obtener provincias únicas para filtro
    provinces = Club.objects.values_list('province', flat=True).distinct().exclude(province='').order_by('province')
    
    context = {
        'page_obj': page_obj,
        'provinces': provinces,
        'selected_province': province,
        'search_query': search_query,
        'has_teams': has_teams,
        'has_active_teams': has_active_teams,
    }
    
    return render(request, 'teams/club_list.html', context)


def club_detail(request, club_id):
    """Detalle de un club con sus equipos"""
    club = get_object_or_404(Club, id=club_id)
    
    # Obtener equipos del club
    teams = club.teams.all().order_by('name')
    
    # Obtener equipos activos
    active_teams = teams.filter(is_active=True)
    
    # Obtener equipos por categoría
    teams_by_category = {}
    for team in active_teams:
        if team.category:
            category_name = team.category.name
            if category_name not in teams_by_category:
                teams_by_category[category_name] = []
            teams_by_category[category_name].append(team)
    
    context = {
        'club': club,
        'teams': teams,
        'active_teams': active_teams,
        'teams_by_category': teams_by_category,
    }
    
    return render(request, 'teams/club_detail.html', context)


def team_list(request):
    """Lista de equipos con filtros"""
    teams = Team.objects.select_related('club', 'category').all()
    
    # Filtros
    club_filter = request.GET.get('club')
    category_filter = request.GET.get('category')
    search_query = request.GET.get('search', '').strip()
    active_only = request.GET.get('active_only', '0') == '1'
    our_teams_only = request.GET.get('our_teams_only', '0') == '1'
    
    # Aplicar filtros
    if club_filter:
        teams = teams.filter(club_id=club_filter)
    
    if category_filter:
        teams = teams.filter(category_id=category_filter)
    
    if search_query:
        teams = teams.filter(
            Q(name__icontains=search_query) |
            Q(federation_id__icontains=search_query) |
            Q(sponsor_name__icontains=search_query) |
            Q(club__official_name__icontains=search_query)
        )
    
    if active_only:
        teams = teams.filter(is_active=True)
    
    if our_teams_only:
        from django.conf import settings
        club_team_names = getattr(settings, 'CLUB_TEAM_NAMES', {})
        teams = teams.filter(name__in=club_team_names.values())
    
    # Paginación
    paginator = Paginator(teams, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Obtener clubs y categorías para filtros
    clubs = Club.objects.filter(teams__isnull=False).distinct().order_by('official_name')
    categories = teams.values_list('category__name', flat=True).distinct().exclude(category__name__isnull=True).order_by('category__name')
    
    context = {
        'page_obj': page_obj,
        'clubs': clubs,
        'categories': categories,
        'selected_club': club_filter,
        'selected_category': category_filter,
        'search_query': search_query,
        'active_only': active_only,
        'our_teams_only': our_teams_only,
    }
    
    return render(request, 'teams/team_list.html', context)


def team_detail(request, team_id):
    """Detalle de un equipo con estadísticas y partidos"""
    team = get_object_or_404(Team, id=team_id)
    
    # Obtener estadísticas del equipo
    stats = team.get_statistics()
    
    # Obtener partidos recientes
    recent_matches = team.get_matches()[:10]
    
    # Obtener clasificaciones
    standings = team.get_standings()[:5]
    
    # Obtener equipos del mismo club
    club_teams = []
    if team.club:
        club_teams = team.club.teams.exclude(id=team.id).filter(is_active=True)[:5]
    
    context = {
        'team': team,
        'stats': stats,
        'recent_matches': recent_matches,
        'standings': standings,
        'club_teams': club_teams,
    }
    
    return render(request, 'teams/team_detail.html', context)


def team_roster(request, team_id):
    """Plantilla de un equipo"""
    team = get_object_or_404(Team, id=team_id)
    
    # Esta funcionalidad se implementará cuando se cree la app rosters
    # Por ahora solo mostrar información básica
    context = {
        'team': team,
        'message': 'Funcionalidad de plantilla en desarrollo - se implementará con la app rosters',
    }
    
    return render(request, 'teams/team_roster.html', context)


@login_required
def team_statistics(request, team_id):
    """Estadísticas detalladas de un equipo (AJAX)"""
    team = get_object_or_404(Team, id=team_id)
    
    try:
        stats = team.get_statistics()
        
        # Obtener partidos por estado
        matches_by_status = {}
        for status, _ in team.get_matches().values_list('status', flat=True).distinct():
            matches_by_status[status] = team.get_matches(status=status).count()
        
        # Obtener partidos por mes (últimos 12 meses)
        from django.db.models import Count
        from django.db.models.functions import TruncMonth
        
        monthly_matches = team.get_matches().annotate(
            month=TruncMonth('match_date')
        ).values('month').annotate(
            count=Count('id')
        ).order_by('-month')[:12]
        
        data = {
            'success': True,
            'stats': stats,
            'matches_by_status': matches_by_status,
            'monthly_matches': list(monthly_matches),
        }
        
    except Exception as e:
        logger.error(f'Error getting team statistics: {e}')
        data = {
            'success': False,
            'error': str(e)
        }
    
    return JsonResponse(data)


def search_teams(request):
    """Búsqueda de equipos (AJAX)"""
    query = request.GET.get('q', '').strip()
    
    if len(query) < 2:
        return JsonResponse({'teams': []})
    
    teams = Team.objects.filter(
        Q(name__icontains=query) |
        Q(club__official_name__icontains=query)
    ).select_related('club', 'category')[:10]
    
    results = []
    for team in teams:
        results.append({
            'id': team.id,
            'name': team.name,
            'club': team.club.official_name if team.club else '',
            'category': team.category.name if team.category else '',
            'is_active': team.is_active,
        })
    
    return JsonResponse({'teams': results})


def search_clubs(request):
    """Búsqueda de clubs (AJAX)"""
    query = request.GET.get('q', '').strip()
    
    if len(query) < 2:
        return JsonResponse({'clubs': []})
    
    clubs = Club.objects.filter(
        Q(official_name__icontains=query) |
        Q(federation_id__icontains=query)
    )[:10]
    
    results = []
    for club in clubs:
        results.append({
            'id': club.id,
            'name': club.official_name,
            'federation_id': club.federation_id,
            'province': club.province,
            'teams_count': club.active_teams_count,
        })
    
    return JsonResponse({'clubs': results})