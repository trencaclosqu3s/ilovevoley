from django.db import models
from django.conf import settings
from django.utils import timezone


class Club(models.Model):
    """Modelo para clubs de voleibol"""
    federation_id = models.CharField(max_length=200, unique=True)
    official_name = models.CharField(max_length=200)
    president = models.CharField(max_length=200, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    venue_name = models.CharField(max_length=200, blank=True)
    venue_address = models.CharField(max_length=200, blank=True)
    province = models.CharField(max_length=100, blank=True)
    instagram = models.URLField(blank=True)
    facebook = models.URLField(blank=True)
    twitter = models.URLField(blank=True)
    website = models.URLField(blank=True)
    logo_url = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['official_name']
        verbose_name = 'Club'
        verbose_name_plural = 'Clubes'

    def __str__(self):
        return self.official_name

    @property
    def logo_federation_url(self):
        """Genera URL del logo basada en federation_id"""
        if self.federation_id:
            return f'https://voleibolib.federatio.com/fichas/clubes/{self.federation_id}.jpg'
        return None

    @property
    def display_logo(self):
        """Devuelve el logo del club (propio o de la federación)"""
        return self.logo_url or self.logo_federation_url

    @property
    def active_teams_count(self):
        """Número de equipos activos del club"""
        return self.teams.filter(is_active=True).count()

    @property
    def total_teams_count(self):
        """Número total de equipos del club"""
        return self.teams.count()

    def get_teams_by_category(self, category_name):
        """Obtiene equipos del club por categoría"""
        return self.teams.filter(
            category__name=category_name,
            is_active=True
        )


class Team(models.Model):
    """Modelo para equipos de voleibol"""
    name = models.CharField(max_length=200)
    federation_id = models.CharField(max_length=200, unique=True)
    club = models.ForeignKey(Club, on_delete=models.SET_NULL, null=True, blank=True, related_name='teams')
    sponsor_name = models.CharField(
        max_length=200, 
        blank=True, 
        help_text='Nombre con patrocinador si aplica'
    )
    logo_url = models.URLField(blank=True, null=True)
    # Foreign key temporal - se actualizará cuando se cree la app content
    category = models.ForeignKey(
        'content.Category', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='teams_teams',
        help_text='Categoría asignada automáticamente durante el scraping'
    )
    is_active = models.BooleanField(
        default=True, 
        help_text='Indica si el equipo sigue activo en las competiciones'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = 'Equipo'
        verbose_name_plural = 'Equipos'

    def __str__(self):
        return self.name

    @property
    def display_logo(self):
        """Devuelve logo del equipo o del club si no tiene"""
        return self.logo_url or (self.club.logo_federation_url if self.club else None)

    @property
    def full_name(self):
        """Nombre completo del equipo (con patrocinador si aplica)"""
        if self.sponsor_name:
            return f"{self.name} - {self.sponsor_name}"
        return self.name

    @property
    def is_our_team(self):
        """Indica si es nuestro equipo (configuración en settings)"""
        from django.conf import settings
        club_team_names = getattr(settings, 'CLUB_TEAM_NAMES', {})
        return self.name in club_team_names.values()

    def get_matches(self, status=None):
        """Obtiene partidos del equipo"""
        from videosvoley.competitions.models import Match
        
        matches = Match.objects.filter(
            models.Q(home_team=self) | models.Q(away_team=self)
        )
        
        if status:
            matches = matches.filter(status=status)
        
        return matches.order_by('-match_date')

    def get_home_matches(self, status=None):
        """Obtiene partidos como local"""
        from videosvoley.competitions.models import Match
        
        matches = Match.objects.filter(home_team=self)
        
        if status:
            matches = matches.filter(status=status)
        
        return matches.order_by('-match_date')

    def get_away_matches(self, status=None):
        """Obtiene partidos como visitante"""
        from videosvoley.competitions.models import Match
        
        matches = Match.objects.filter(away_team=self)
        
        if status:
            matches = matches.filter(status=status)
        
        return matches.order_by('-match_date')

    def get_standings(self, league=None):
        """Obtiene clasificaciones del equipo"""
        from videosvoley.competitions.models import Standing
        
        standings = Standing.objects.filter(team=self)
        
        if league:
            standings = standings.filter(league=league)
        
        return standings.order_by('-league__created_at')

    def get_statistics(self):
        """Obtiene estadísticas del equipo"""
        matches = self.get_matches()
        finished_matches = matches.filter(status='finished')
        
        stats = {
            'total_matches': matches.count(),
            'finished_matches': finished_matches.count(),
            'scheduled_matches': matches.filter(status='scheduled').count(),
            'wins': 0,
            'losses': 0,
            'win_percentage': 0,
        }
        
        for match in finished_matches:
            if match.home_team == self:
                if match.home_score and match.away_score:
                    if match.home_score > match.away_score:
                        stats['wins'] += 1
                    else:
                        stats['losses'] += 1
            else:  # away_team
                if match.home_score and match.away_score:
                    if match.away_score > match.home_score:
                        stats['wins'] += 1
                    else:
                        stats['losses'] += 1
        
        total_played = stats['wins'] + stats['losses']
        if total_played > 0:
            stats['win_percentage'] = round((stats['wins'] / total_played) * 100, 1)
        
        return stats


class TeamManager(models.Manager):
    """Manager personalizado para equipos"""
    
    def active(self):
        """Equipos activos"""
        return self.filter(is_active=True)
    
    def by_category(self, category):
        """Equipos por categoría"""
        return self.filter(category=category, is_active=True)
    
    def by_club(self, club):
        """Equipos por club"""
        return self.filter(club=club, is_active=True)
    
    def our_teams(self):
        """Nuestros equipos (configuración en settings)"""
        from django.conf import settings
        club_team_names = getattr(settings, 'CLUB_TEAM_NAMES', {})
        return self.filter(name__in=club_team_names.values())


class ClubManager(models.Manager):
    """Manager personalizado para clubs"""
    
    def with_teams(self):
        """Clubs que tienen equipos"""
        return self.filter(teams__isnull=False).distinct()
    
    def with_active_teams(self):
        """Clubs con equipos activos"""
        return self.filter(teams__is_active=True).distinct()
    
    def by_province(self, province):
        """Clubs por provincia"""
        return self.filter(province__icontains=province)