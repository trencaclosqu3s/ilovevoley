from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import FileExtensionValidator
import re
import os


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
        """Convierte URL de YouTube normal en URL de embed con privacidad mejorada"""
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)',
            r'youtube\.com\/embed\/([^&\n?#]+)',
            r'youtube\.com\/live\/([^&\n?#]+)',  # Patrón para livestreams
        ]

        for pattern in patterns:
            match = re.search(pattern, self.youtube_url)
            if match:
                video_id = match.group(1)
                # Parámetros para máxima privacidad:
                # - rel=0: no mostrar vídeos relacionados
                # - modestbranding=1: minimizar branding de YouTube
                # - fs=1: permitir pantalla completa
                # - enablejsapi=0: deshabilitar API de JavaScript
                return f'https://www.youtube-nocookie.com/embed/{video_id}?rel=0&modestbranding=1&fs=1&enablejsapi=0'

        return self.youtube_url
    
    def is_livestream(self):
        """Detecta si es un livestream de YouTube"""
        return 'youtube.com/live/' in self.youtube_url or '/live/' in self.youtube_url
    
    def get_video_type(self):
        """Devuelve el tipo de vídeo para mostrar mensajes apropiados"""
        if self.is_livestream():
            return 'livestream'
        return 'video'


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


class Club(models.Model):
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


class Team(models.Model):
    name = models.CharField(max_length=200)
    federation_id = models.CharField(max_length=200, unique=True)
    club = models.ForeignKey(Club, on_delete=models.SET_NULL, null=True, blank=True, related_name='teams')
    sponsor_name = models.CharField(max_length=200, blank=True, help_text='Nombre con patrocinador si aplica')
    logo_url = models.URLField(blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='teams', help_text='Categoría asignada automáticamente durante el scraping')
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


def image_upload_path(instance, filename):
    """Genera ruta de subida para imágenes organizadas por año y mes"""
    year = timezone.now().year
    month = timezone.now().month
    # Mantener extensión original pero limpiar el nombre
    name, ext = os.path.splitext(filename)
    clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    return f'images/{year}/{month:02d}/{clean_name}{ext}'


class Image(models.Model):
    MODERATION_STATUS = [
        ('pending', 'Pendiente de Moderación'),
        ('approved', 'Aprobada'),
        ('rejected', 'Rechazada'),
    ]
    
    IMAGE_TYPES = [
        ('match', 'Partido'),
        ('celebration', 'Celebración'),
        ('training', 'Entrenamiento'),
        ('team_photo', 'Foto de Equipo'),
        ('facilities', 'Instalaciones'),
        ('other', 'Otro'),
    ]
    
    image = models.ImageField(
        upload_to=image_upload_path,
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp'])],
        help_text='Formatos permitidos: JPG, PNG, WebP. Tamaño máximo: 10MB'
    )
    title = models.CharField(max_length=200, help_text='Título descriptivo de la imagen')
    description = models.TextField(blank=True, help_text='Descripción opcional')
    
    # Tipo y etiquetas
    image_type = models.CharField(
        max_length=20,
        choices=IMAGE_TYPES,
        default='other',
        help_text='Tipo de imagen'
    )
    tags = models.CharField(
        max_length=500,
        blank=True,
        help_text='Etiquetas separadas por comas (ej: gol, victoria, senior)'
    )
    auto_tags = models.JSONField(
        default=list,
        blank=True,
        help_text='Etiquetas detectadas automáticamente por Vision API'
    )
    
    # Relaciones
    match = models.ForeignKey(
        'Match', 
        on_delete=models.CASCADE, 
        null=True,
        blank=True,
        related_name='images',
        help_text='Partido al que pertenece la imagen (opcional)'
    )
    categories = models.ManyToManyField(
        Category,
        blank=True,
        related_name='images',
        help_text='Categorías asociadas a la imagen. Se asigna automáticamente desde el partido o manualmente'
    )
    year = models.IntegerField(help_text='Año de la temporada')
    
    # Metadatos
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        related_name='uploaded_images'
    )
    upload_date = models.DateTimeField(auto_now_add=True)
    
    # Moderación
    status = models.CharField(
        max_length=20, 
        choices=MODERATION_STATUS, 
        default='pending',
        help_text='Estado de moderación'
    )
    moderated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='moderated_images'
    )
    moderation_date = models.DateTimeField(null=True, blank=True)
    moderation_notes = models.TextField(
        blank=True,
        help_text='Notas internas de moderación'
    )
    
    # Google Vision API (opcional)
    vision_api_checked = models.BooleanField(default=False)
    vision_api_safe = models.BooleanField(default=True)
    vision_api_details = models.JSONField(default=dict, blank=True)
    
    class Meta:
        ordering = ['-upload_date']
        verbose_name = 'Imagen'
        verbose_name_plural = 'Imágenes'
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['match']),
            models.Index(fields=['year']),
            models.Index(fields=['upload_date']),
            models.Index(fields=['image_type']),
        ]

    def __str__(self):
        if self.match:
            return f'{self.title} - {self.match}'
        return f'{self.title} ({self.get_image_type_display()})'

    def save(self, *args, **kwargs):
        # Determinar si es una creación nueva
        is_new = self.pk is None
        
        # Auto-asignar año desde el partido si está vinculado
        if self.match:
            # Extraer año de la fecha del partido o temporada
            if hasattr(self.match, 'match_date') and self.match.match_date:
                self.year = self.match.match_date.year
            elif hasattr(self.match.league, 'season'):
                # Extraer año de temporada (ej: "2024-25" -> 2024)
                try:
                    self.year = int(self.match.league.season.split('-')[0])
                except (ValueError, IndexError):
                    self.year = timezone.now().year
            else:
                self.year = timezone.now().year
            
            # Si es una imagen de partido pero no se especificó el tipo, asignarlo
            if self.image_type == 'other':
                self.image_type = 'match'
        else:
            # Para imágenes sin partido, usar año actual si no se especifica
            if not self.year:
                self.year = timezone.now().year
        
        super().save(*args, **kwargs)
        
        # Después de guardar, asignar categorías desde el partido si es nueva y no tiene categorías
        if is_new and self.match and not self.categories.exists():
            if self.match.league and self.match.league.category:
                self.categories.add(self.match.league.category)
            # También agregar categorías de los equipos si las tienen
            if self.match.home_team and self.match.home_team.category:
                self.categories.add(self.match.home_team.category)
            if self.match.away_team and self.match.away_team.category:
                self.categories.add(self.match.away_team.category)

    @property
    def is_approved(self):
        return self.status == 'approved'
    
    @property
    def is_pending(self):
        return self.status == 'pending'
    
    @property
    def thumbnail_url(self):
        """URL para thumbnail - se puede implementar con django-imagekit"""
        return self.image.url if self.image else None
        
    def moderate(self, moderator, approved=True, notes=''):
        """Helper para moderar la imagen"""
        self.status = 'approved' if approved else 'rejected'
        self.moderated_by = moderator
        self.moderation_date = timezone.now()
        self.moderation_notes = notes
        self.save()
    
    @property
    def all_tags(self):
        """Combina etiquetas manuales y automáticas"""
        manual_tags = [tag.strip() for tag in self.tags.split(',') if tag.strip()]
        auto_tags = self.auto_tags if isinstance(self.auto_tags, list) else []
        return list(set(manual_tags + auto_tags))
    
    @property
    def tags_display(self):
        """Devuelve etiquetas formateadas para mostrar"""
        return ', '.join(self.all_tags)
    
    @property
    def categories_display(self):
        """Devuelve las categorías formateadas para mostrar"""
        return ', '.join([cat.name for cat in self.categories.all()])
    
    def get_category_list(self):
        """Devuelve lista de categorías"""
        return list(self.categories.all())
    
    def add_auto_tags(self, tags_list):
        """Agrega etiquetas automáticas sin duplicar"""
        if not isinstance(tags_list, list):
            return
        current_auto_tags = self.auto_tags if isinstance(self.auto_tags, list) else []
        # Combinar y eliminar duplicados manteniendo orden
        combined = current_auto_tags + [tag for tag in tags_list if tag not in current_auto_tags]
        self.auto_tags = combined