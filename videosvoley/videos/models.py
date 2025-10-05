from django.db import models
from django.conf import settings
from django.utils import timezone
import re


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Categoría'
        verbose_name_plural = 'Categorías'

    def __str__(self):
        return self.name


class Video(models.Model):
    title = models.CharField(max_length=200)
    youtube_url = models.URLField()
    description = models.TextField(blank=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, null=True, blank=True)
    match = models.ForeignKey('Match', on_delete=models.SET_NULL, null=True, blank=True, related_name='videos')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def get_embed_url(self):
        """Convierte URL de YouTube normal en URL de embed"""
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)',
            r'youtube\.com\/embed\/([^&\n?#]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, self.youtube_url)
            if match:
                video_id = match.group(1)
                return f'https://www.youtube-nocookie.com/embed/{video_id}?rel=0&modestbranding=1&fs=1'

        return self.youtube_url


class Comment(models.Model):
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.user.username} - {self.content[:50]}...'


class League(models.Model):
    COMPETITION_TYPES = [
        ('regular', 'Liga Regular'),
        ('playoff', 'Playoff'),
        ('cup', 'Copa'),
        ('friendly', 'Amistoso'),
    ]
    
    name = models.CharField(max_length=200)
    federation_id = models.CharField(max_length=200, unique=True)
    competition_type = models.CharField(max_length=20, choices=COMPETITION_TYPES, default='regular')
    season = models.CharField(max_length=20)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='leagues')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    base_url = models.URLField(default='https://www.voleibolib.net')
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Liga'
        verbose_name_plural = 'Ligas'
        unique_together = ['federation_id', 'season']

    def __str__(self):
        return f'{self.name} ({self.season})'


class Team(models.Model):
    name = models.CharField(max_length=200)
    federation_id = models.CharField(max_length=200, unique=True)
    logo_url = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = 'Equipo'
        verbose_name_plural = 'Equipos'

    def __str__(self):
        return self.name


class Match(models.Model):
    MATCH_STATES = [
        ('scheduled', 'Programado'),
        ('in_progress', 'En Progreso'),
        ('finished', 'Finalizado'),
        ('postponed', 'Aplazado'),
        ('cancelled', 'Cancelado'),
    ]
    
    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name='matches')
    home_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='home_matches')
    away_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='away_matches')
    match_date = models.DateTimeField()
    venue = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    round_number = models.IntegerField(default=1)
    home_score = models.IntegerField(null=True, blank=True)
    away_score = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=MATCH_STATES, default='scheduled')
    federation_id = models.CharField(max_length=200, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['match_date']
        verbose_name = 'Partido'
        verbose_name_plural = 'Partidos'

    def __str__(self):
        return f'{self.home_team} vs {self.away_team} - {self.match_date.strftime("%d/%m/%Y")}'

    @property
    def is_finished(self):
        return self.status == 'finished'

    @property
    def result_display(self):
        if self.home_score is not None and self.away_score is not None:
            return f'{self.home_score} - {self.away_score}'
        return 'Sin resultado'


class ScrapingEndpoint(models.Model):
    ENDPOINT_TYPES = [
        ('standings', 'Clasificación'),
        ('results', 'Resultados'),
        ('calendar', 'Calendario'),
    ]
    
    PARSER_TYPES = [
        ('table_standings', 'Tabla de Clasificación'),
        ('match_results', 'Resultados de Partidos'),
        ('match_calendar', 'Calendario de Partidos'),
    ]
    
    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name='endpoints')
    endpoint_type = models.CharField(max_length=20, choices=ENDPOINT_TYPES)
    url_pattern = models.CharField(max_length=500, help_text='Usar {league_id}, {round}, etc. para parámetros dinámicos')
    parser_type = models.CharField(max_length=30, choices=PARSER_TYPES)
    is_active = models.BooleanField(default=True)
    extra_params = models.JSONField(default=dict, blank=True, help_text='Parámetros adicionales como JSON')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Endpoint de Scraping'
        verbose_name_plural = 'Endpoints de Scraping'
        unique_together = ['league', 'endpoint_type']

    def __str__(self):
        return f'{self.league.name} - {self.get_endpoint_type_display()}'

    def get_full_url(self, **kwargs):
        """Construye la URL completa reemplazando parámetros"""
        url = self.url_pattern.format(league_id=self.league.federation_id, **kwargs)
        if not url.startswith('http'):
            url = f'{self.league.base_url}/{url.lstrip("/")}'
        return url


class Standing(models.Model):
    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name='standings')
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='standings')
    position = models.IntegerField()
    played = models.IntegerField(default=0)
    won = models.IntegerField(default=0)
    lost = models.IntegerField(default=0)
    sets_for = models.IntegerField(default=0)
    sets_against = models.IntegerField(default=0)
    points_for = models.IntegerField(default=0)
    points_against = models.IntegerField(default=0)
    total_points = models.IntegerField(default=0)
    wins_3_0 = models.IntegerField(default=0, verbose_name='Victorias 3-0')
    wins_3_1 = models.IntegerField(default=0, verbose_name='Victorias 3-1')
    wins_3_2 = models.IntegerField(default=0, verbose_name='Victorias 3-2')
    losses_2_3 = models.IntegerField(default=0, verbose_name='Derrotas 2-3')
    losses_1_3 = models.IntegerField(default=0, verbose_name='Derrotas 1-3')
    losses_0_3 = models.IntegerField(default=0, verbose_name='Derrotas 0-3')
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['position']
        verbose_name = 'Clasificación'
        verbose_name_plural = 'Clasificaciones'
        unique_together = ['league', 'team']

    def __str__(self):
        return f'{self.position}. {self.team.name} - {self.total_points} pts'

    @property
    def set_difference(self):
        return self.sets_for - self.sets_against

    @property
    def point_difference(self):
        return self.points_for - self.points_against