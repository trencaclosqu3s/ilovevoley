from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import FileExtensionValidator
from django.contrib.auth import get_user_model
import re
import os

User = get_user_model()


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


class LeagueManager(models.Manager):
    """Manager personalizado para League con métodos de filtrado"""

    def visible_in_app(self):
        """Ligas que deben mostrarse en la aplicación principal"""
        return self.filter(
            is_active=True,
            visibility_type='main',
            is_our_team_related=True
        )

    def reference_leagues(self):
        """Ligas de referencia (solo admin)"""
        return self.filter(
            visibility_type__in=['reference', 'historical', 'external']
        )

    def historical_leagues(self):
        """Ligas históricas"""
        return self.filter(
            visibility_type='historical',
            is_historical=True
        )

    def external_leagues(self):
        """Ligas externas (no relacionadas con nuestro equipo)"""
        return self.filter(
            visibility_type='external',
            is_our_team_related=False
        )

    def all_for_admin(self):
        """Todas las ligas para el admin"""
        return self.all()


class League(models.Model):
    COMPETITION_TYPES = [
        ('regular', 'Liga Regular'),
        ('playoff', 'Playoff'),
        ('cup', 'Copa'),
        ('friendly', 'Amistoso'),
    ]
    
    VISIBILITY_TYPES = [
        ('main', 'Principal (mostrar en app)'),
        ('reference', 'Referencia (solo admin)'),
        ('historical', 'Histórica (solo admin)'),
        ('external', 'Externa (solo admin)'),
    ]
    
    name = models.CharField(max_length=200)
    federation_id = models.CharField(max_length=200, unique=True)
    competition_type = models.CharField(max_length=20, choices=COMPETITION_TYPES, default='regular')
    season = models.CharField(max_length=20)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='leagues')
    is_active = models.BooleanField(default=True)
    visibility_type = models.CharField(
        max_length=20, 
        choices=VISIBILITY_TYPES, 
        default='main',
        help_text='Controla dónde se muestra la liga: Principal (en la app), Referencia (solo admin), Histórica (datos antiguos), Externa (otras ligas)'
    )
    is_historical = models.BooleanField(
        default=False,
        help_text='Indica si es una liga de temporadas anteriores'
    )
    is_our_team_related = models.BooleanField(
        default=True,
        help_text='Indica si esta liga está relacionada con nuestro equipo'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    base_url = models.URLField(default='https://www.voleibolib.net')
    
    objects = LeagueManager()
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Liga'
        verbose_name_plural = 'Ligas'
        unique_together = ['federation_id', 'season']

    def __str__(self):
        return f'{self.name} ({self.season})'
    
    @property
    def has_pending_matches(self):
        """Indica si la liga tiene partidos pendientes (programados o en curso)"""
        from django.utils import timezone
        now = timezone.now()
        return self.matches.filter(
            status__in=['scheduled', 'in_progress'],
            match_date__gte=now
        ).exists()
    
    @property
    def should_show_in_app(self):
        """Indica si la liga debe mostrarse en la aplicación principal"""
        return (
            self.is_active and 
            self.visibility_type == 'main' and 
            self.is_our_team_related
        )
    
    @property
    def is_reference_league(self):
        """Indica si es una liga de referencia (solo para admin)"""
        return self.visibility_type in ['reference', 'historical', 'external']
    
    @property
    def is_past_league(self):
        """Indica si la liga es del pasado (sin partidos pendientes)"""
        return not self.has_pending_matches


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
    is_active = models.BooleanField(default=True, help_text='Indica si el equipo sigue activo en las competiciones')
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


class MatchManager(models.Manager):
    """Manager personalizado que excluye partidos withdrawn por defecto"""
    def get_queryset(self):
        return super().get_queryset().exclude(status='withdrawn')


class MatchAllManager(models.Manager):
    """Manager que incluye TODOS los partidos, incluyendo withdrawn"""
    pass


class Match(models.Model):
    MATCH_STATES = [
        ('scheduled', 'Programado'),
        ('in_progress', 'En Progreso'),
        ('finished', 'Finalizado'),
        ('postponed', 'Aplazado'),
        ('cancelled', 'Cancelado'),
        ('withdrawn', 'Retirado (equipo fuera de liga)'),
    ]
    
    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name='matches', null=True, blank=True)
    home_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='home_matches', null=True, blank=True)
    away_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='away_matches', null=True, blank=True)
    
    # Campos para partidos amistosos con equipos no registrados
    home_team_text = models.CharField(
        max_length=200, 
        blank=True, 
        help_text='Nombre del equipo local para partidos amistosos sin equipo en BD'
    )
    away_team_text = models.CharField(
        max_length=200, 
        blank=True, 
        help_text='Nombre del equipo visitante para partidos amistosos sin equipo en BD'
    )
    is_friendly = models.BooleanField(
        default=False,
        help_text='Indica si es un partido amistoso creado manualmente'
    )
    match_date = models.DateTimeField()
    venue = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    round_number = models.IntegerField(default=1)
    home_score = models.IntegerField(null=True, blank=True)
    away_score = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=MATCH_STATES, default='scheduled')
    federation_id = models.CharField(max_length=200, unique=True, null=True, blank=True)
    
    # Información de árbitros y personal técnico
    referee1 = models.CharField(max_length=200, blank=True, verbose_name='Árbitro 1')
    referee2 = models.CharField(max_length=200, blank=True, verbose_name='Árbitro 2')
    scorer = models.CharField(max_length=200, blank=True, verbose_name='Anotador')
    timekeeper = models.CharField(max_length=200, blank=True, verbose_name='Cronometrador')
    delegate = models.CharField(max_length=200, blank=True, verbose_name='Delegado')
    
    # Información detallada del campo
    field_address = models.CharField(max_length=500, blank=True, verbose_name='Dirección del Campo')
    
    # IDs de la federación para matching
    federation_club_local_id = models.CharField(max_length=50, blank=True, verbose_name='ID Club Local (Federación)')
    federation_club_away_id = models.CharField(max_length=50, blank=True, verbose_name='ID Club Visitante (Federación)')
    
    # Información de acta oficial
    acta_html = models.CharField(max_length=200, blank=True, verbose_name='Acta HTML')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Managers
    objects = MatchManager()  # Manager por defecto: excluye withdrawn
    all_objects = MatchAllManager()  # Manager completo: incluye withdrawn
    
    class Meta:
        ordering = ['match_date']
        verbose_name = 'Partido'
        verbose_name_plural = 'Partidos'

    def __str__(self):
        return f'{self.home_team_display} vs {self.away_team_display} - {self.match_date.strftime("%d/%m/%Y")}'

    @property
    def is_finished(self):
        return self.status == 'finished'

    @property
    def result_display(self):
        if self.home_score is not None and self.away_score is not None:
            return f'{self.home_score} - {self.away_score}'
        return 'Sin resultado'
    
    @property
    def home_team_display(self):
        """Retorna el nombre del equipo local (Team o texto)"""
        if self.home_team:
            return self.home_team.name
        return self.home_team_text or 'Equipo Local'

    @property
    def away_team_display(self):
        """Retorna el nombre del equipo visitante (Team o texto)"""
        if self.away_team:
            return self.away_team.name
        return self.away_team_text or 'Equipo Visitante'

    @property
    def is_official(self):
        """Indica si es un partido oficial (scrapeado)"""
        return not self.is_friendly and self.federation_id is not None
    
    def clean(self):
        """Validar consistencia de los campos del partido"""
        from django.core.exceptions import ValidationError
        
        # Solo validar equipos para partidos NO amistosos que no estén en proceso de creación
        # Para amistosos, el formulario ya se encarga de la validación
        if not self.is_friendly and self.pk is not None:
            # Validar equipo local para partidos oficiales ya guardados
            if not self.home_team and not self.home_team_text:
                raise ValidationError('Debe especificar un equipo local (seleccionado o texto)')
            
            # Validar equipo visitante para partidos oficiales ya guardados
            if not self.away_team and not self.away_team_text:
                raise ValidationError('Debe especificar un equipo visitante (seleccionado o texto)')
        
        # Si es amistoso, validar que no tenga federation_id
        if self.is_friendly and self.federation_id:
            raise ValidationError('Los partidos amistosos no deben tener federation_id')
        
        # Si tiene federation_id, no debe ser amistoso
        if self.federation_id and self.is_friendly:
            self.is_friendly = False  # Auto-corregir


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
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp', 'heic', 'heif'])],
        help_text='Formatos permitidos: JPG, PNG, WebP, HEIC. Tamaño máximo: 10MB'
    )
    title = models.CharField(max_length=200, help_text='Título descriptivo de la imagen')
    description = models.TextField(blank=True, help_text='Descripción opcional')
    
    # Campos para tracking de conversión de formato
    original_format = models.CharField(
        max_length=10,
        blank=True,
        help_text='Formato original del archivo (ej: heic, jpg)'
    )
    was_converted = models.BooleanField(
        default=False,
        help_text='Indica si la imagen fue convertida desde otro formato'
    )
    
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


def player_photo_upload_path(instance, filename):
    """Genera ruta de subida para fotos de jugadores organizadas por equipo"""
    team_name = re.sub(r'[^a-zA-Z0-9_-]', '_', instance.team.name.lower())
    name, ext = os.path.splitext(filename)
    clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    return f'players/{team_name}/{clean_name}{ext}'


def staff_photo_upload_path(instance, filename):
    """Genera ruta de subida para fotos de staff organizadas por equipo"""
    team_name = re.sub(r'[^a-zA-Z0-9_-]', '_', instance.team.name.lower())
    name, ext = os.path.splitext(filename)
    clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    return f'staff/{team_name}/{clean_name}{ext}'


class Player(models.Model):
    POSITION_CHOICES = [
        ('setter', 'Colocador'),
        ('outside_hitter', 'Receptor'),
        ('middle_blocker', 'Central'),
        ('opposite', 'Opuesto'),
        ('libero', 'Líbero'),
    ]
    
    # Campos obligatorios
    first_name = models.CharField(max_length=100, verbose_name='Nombre')
    last_name = models.CharField(max_length=100, verbose_name='Apellidos')
    team = models.ForeignKey(
        Team, 
        on_delete=models.CASCADE, 
        related_name='players',
        verbose_name='Equipo'
    )
    
    # Campos opcionales
    jersey_number = models.PositiveSmallIntegerField(
        null=True, 
        blank=True,
        verbose_name='Número de Dorsal',
        help_text='Número de la camiseta (opcional)'
    )
    position = models.CharField(
        max_length=20, 
        choices=POSITION_CHOICES, 
        blank=True,
        verbose_name='Posición',
        help_text='Posición principal del jugador (opcional)'
    )
    birth_date = models.DateField(
        null=True, 
        blank=True,
        verbose_name='Fecha de Nacimiento',
        help_text='Fecha de nacimiento del jugador (opcional)'
    )
    photo = models.ImageField(
        upload_to=player_photo_upload_path,
        null=True,
        blank=True,
        verbose_name='Foto',
        help_text='Foto del jugador (opcional)',
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp'])]
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='player_profile',
        verbose_name='Usuario Vinculado',
        help_text='Usuario de la plataforma asociado al jugador (opcional)'
    )
    
    # Metadatos
    is_active = models.BooleanField(
        default=True,
        verbose_name='Activo',
        help_text='Indica si el jugador está actualmente en el equipo'
    )
    notes = models.TextField(
        blank=True,
        verbose_name='Notas',
        help_text='Notas adicionales sobre el jugador'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de Creación')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Última Actualización')
    
    class Meta:
        ordering = ['jersey_number', 'last_name', 'first_name']
        verbose_name = 'Jugador'
        verbose_name_plural = 'Jugadores'
        unique_together = [['team', 'jersey_number']]  # Un número por equipo
        indexes = [
            models.Index(fields=['team', 'is_active']),
            models.Index(fields=['position']),
        ]

    def __str__(self):
        number_str = f"#{self.jersey_number} " if self.jersey_number else ""
        return f"{number_str}{self.first_name} {self.last_name}"

    @property
    def full_name(self):
        """Devuelve el nombre completo"""
        return f"{self.first_name} {self.last_name}"
    
    @property
    def age(self):
        """Calcula la edad del jugador"""
        if not self.birth_date:
            return None
        today = timezone.now().date()
        return today.year - self.birth_date.year - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))
    
    @property
    def display_position(self):
        """Devuelve la posición en formato legible"""
        return self.get_position_display() if self.position else 'Sin asignar'
    
    def clean(self):
        """Validación personalizada"""
        from django.core.exceptions import ValidationError
        
        # Validar que el número de dorsal sea único en el equipo
        if self.jersey_number is not None:
            existing = Player.objects.filter(
                team=self.team, 
                jersey_number=self.jersey_number,
                is_active=True
            ).exclude(pk=self.pk)
            
            if existing.exists():
                raise ValidationError({
                    'jersey_number': f'El número {self.jersey_number} ya está asignado a otro jugador activo en este equipo.'
                })


class Staff(models.Model):
    STAFF_ROLES = [
        ('head_coach', 'Entrenador/a'),
        ('assistant_coach', 'Segundo Entrenador/a'),
        ('delegate', 'Delegado/a'),
        ('other', 'Otro'),
    ]
    
    # Campos obligatorios
    first_name = models.CharField(max_length=100, verbose_name='Nombre')
    last_name = models.CharField(max_length=100, verbose_name='Apellidos')
    team = models.ForeignKey(
        Team, 
        on_delete=models.CASCADE, 
        related_name='staff',
        verbose_name='Equipo'
    )
    role = models.CharField(
        max_length=20, 
        choices=STAFF_ROLES,
        verbose_name='Rol',
        help_text='Función que desempeña en el equipo'
    )
    
    # Campos opcionales
    photo = models.ImageField(
        upload_to=staff_photo_upload_path,
        null=True,
        blank=True,
        verbose_name='Foto',
        help_text='Foto del miembro del staff (opcional)',
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp'])]
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='staff_profile',
        verbose_name='Usuario Vinculado',
        help_text='Usuario de la plataforma asociado al miembro del staff (opcional)'
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name='Teléfono',
        help_text='Número de contacto (opcional)'
    )
    email = models.EmailField(
        blank=True,
        verbose_name='Email',
        help_text='Correo electrónico de contacto (opcional)'
    )
    
    # Metadatos
    is_active = models.BooleanField(
        default=True,
        verbose_name='Activo',
        help_text='Indica si el miembro del staff está actualmente en el equipo'
    )
    notes = models.TextField(
        blank=True,
        verbose_name='Notas',
        help_text='Notas adicionales sobre el miembro del staff'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de Creación')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Última Actualización')
    
    class Meta:
        ordering = ['role', 'last_name', 'first_name']
        verbose_name = 'Miembro del Staff'
        verbose_name_plural = 'Staff'
        indexes = [
            models.Index(fields=['team', 'is_active']),
            models.Index(fields=['role']),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.get_role_display()})"

    @property
    def full_name(self):
        """Devuelve el nombre completo"""
        return f"{self.first_name} {self.last_name}"
    
    @property
    def display_role(self):
        """Devuelve el rol en formato legible"""
        return self.get_role_display()


# =============================================================================
# NUEVA ESTRUCTURA: PERSON-ROLE (Reemplaza Player y Staff)
# =============================================================================

def person_photo_upload_path(instance, filename):
    """Generar path para la subida de fotos de personas"""
    import os
    from django.utils.text import slugify
    
    ext = filename.split('.')[-1]
    safe_name = slugify(f"{instance.first_name}_{instance.last_name}")
    return f'people/{safe_name}_{instance.id}.{ext}'


class Person(models.Model):
    """
    Modelo base para todas las personas del club (jugadores, staff, etc.)
    Una persona puede tener múltiples roles en diferentes equipos.
    """
    # Información personal básica
    first_name = models.CharField(
        max_length=100, 
        verbose_name='Nombre',
        help_text='Nombre de la persona'
    )
    last_name = models.CharField(
        max_length=100, 
        verbose_name='Apellidos',
        help_text='Apellidos de la persona'
    )
    birth_date = models.DateField(
        null=True, 
        blank=True, 
        verbose_name='Fecha de Nacimiento',
        help_text='Fecha de nacimiento (opcional)'
    )
    photo = models.ImageField(
        upload_to=person_photo_upload_path,
        null=True,
        blank=True,
        verbose_name='Foto',
        help_text='Foto de la persona (opcional)'
    )
    
    # Información de contacto
    email = models.EmailField(
        blank=True,
        verbose_name='Email',
        help_text='Dirección de email (opcional)'
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name='Teléfono',
        help_text='Número de teléfono (opcional)'
    )
    
    # Vinculación con usuario de la plataforma
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Usuario Vinculado',
        help_text='Usuario de la plataforma asociado (opcional)'
    )
    
    # Notas y observaciones
    notes = models.TextField(
        blank=True,
        verbose_name='Notas',
        help_text='Notas adicionales sobre la persona'
    )
    
    # Estado y metadata
    is_active = models.BooleanField(
        default=True,
        verbose_name='Activo',
        help_text='¿Está activo en el club?'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creado')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Actualizado')

    class Meta:
        ordering = ['last_name', 'first_name']
        verbose_name = 'Ficha'
        verbose_name_plural = 'Fichas'
        indexes = [
            models.Index(fields=['last_name', 'first_name']),
            models.Index(fields=['is_active']),
            models.Index(fields=['created_at']),
        ]
        # Evitar duplicados exactos
        constraints = [
            models.UniqueConstraint(
                fields=['first_name', 'last_name', 'birth_date'],
                name='unique_person_identity',
                condition=models.Q(birth_date__isnull=False)
            )
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def full_name(self):
        """Devuelve el nombre completo"""
        return f"{self.first_name} {self.last_name}"
    
    @property
    def age(self):
        """Calcula la edad basada en la fecha de nacimiento"""
        if not self.birth_date:
            return None
        from datetime import date
        today = date.today()
        return today.year - self.birth_date.year - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))
    
    @property
    def age_display(self):
        """Muestra la edad de forma legible"""
        age = self.age
        return f"{age} años" if age is not None else "No especificada"
    
    @property
    def photo_preview(self):
        """Preview de la foto para el admin"""
        if self.photo:
            from django.utils.html import format_html
            return format_html('<img src="{}" width="50" height="50" style="object-fit: cover; border-radius: 4px;" />', self.photo.url)
        return "Sin foto"
    
    @property
    def contact_info(self):
        """Información de contacto resumida"""
        contact_parts = []
        if self.email:
            contact_parts.append(self.email)
        if self.phone:
            contact_parts.append(self.phone)
        return " / ".join(contact_parts) or "Sin contacto"
    
    def get_player_roles(self):
        """Obtiene todos los roles de jugador de esta persona"""
        return self.player_roles.filter(is_active=True).select_related('team', 'team__category')
    
    def get_staff_roles(self):
        """Obtiene todos los roles de staff de esta persona"""
        return self.staff_roles.filter(is_active=True).select_related('team', 'team__category')
    
    def get_all_active_teams(self):
        """Obtiene todos los equipos donde tiene roles activos"""
        from django.db.models import Q
        player_teams = Team.objects.filter(player_roles__person=self, player_roles__is_active=True)
        staff_teams = Team.objects.filter(staff_roles__person=self, staff_roles__is_active=True)
        return Team.objects.filter(Q(id__in=player_teams) | Q(id__in=staff_teams)).distinct()


class PlayerRole(models.Model):
    """
    Rol de jugador de una persona en un equipo específico.
    Una persona puede ser jugador en múltiples equipos.
    """
    POSITION_CHOICES = [
        ('setter', 'Colocador'),
        ('outside_hitter', 'Receptor'),
        ('middle_blocker', 'Central'),
        ('opposite', 'Opuesto'),
        ('libero', 'Líbero'),
    ]
    
    # Relaciones
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name='player_roles',
        verbose_name='Persona'
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='player_roles',
        verbose_name='Equipo'
    )
    
    # Información específica del rol de jugador
    jersey_number = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name='Número de Dorsal',
        help_text='Número de la camiseta (opcional)'
    )
    position = models.CharField(
        max_length=20,
        choices=POSITION_CHOICES,
        blank=True,
        verbose_name='Posición',
        help_text='Posición preferida (opcional)'
    )
    
    # Estado y metadata
    is_active = models.BooleanField(
        default=True,
        verbose_name='Activo',
        help_text='¿Está actualmente jugando en este equipo?'
    )
    notes = models.TextField(
        blank=True,
        verbose_name='Notas',
        help_text='Notas específicas sobre este rol'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creado')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Actualizado')

    class Meta:
        ordering = ['team', 'jersey_number', 'person__last_name', 'person__first_name']
        verbose_name = 'Rol de Jugador'
        verbose_name_plural = 'Roles de Jugador'
        indexes = [
            models.Index(fields=['team', 'is_active']),
            models.Index(fields=['person', 'is_active']),
            models.Index(fields=['jersey_number']),
            models.Index(fields=['position']),
        ]
        # Evitar duplicados de persona-equipo activos
        constraints = [
            models.UniqueConstraint(
                fields=['person', 'team'],
                name='unique_active_player_role',
                condition=models.Q(is_active=True)
            ),
            # Evitar números de dorsal duplicados en el mismo equipo
            models.UniqueConstraint(
                fields=['team', 'jersey_number'],
                name='unique_jersey_number_per_team',
                condition=models.Q(jersey_number__isnull=False, is_active=True)
            )
        ]

    def __str__(self):
        jersey_info = f" (#{self.jersey_number})" if self.jersey_number else ""
        return f"{self.person.full_name}{jersey_info} - {self.team.name}"
    
    @property
    def display_position(self):
        """Devuelve la posición en formato legible"""
        return self.get_position_display() if self.position else "Sin posición"


class StaffRole(models.Model):
    """
    Rol de staff de una persona en un equipo específico.
    Una persona puede tener roles de staff en múltiples equipos.
    """
    STAFF_ROLES = [
        ('head_coach', 'Entrenador/a'),
        ('assistant_coach', 'Segundo Entrenador/a'),
        ('delegate', 'Delegado/a'),
        ('other', 'Otro'),
    ]
    
    # Relaciones
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name='staff_roles',
        verbose_name='Persona'
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='staff_roles',
        verbose_name='Equipo'
    )
    
    # Información específica del rol de staff
    role = models.CharField(
        max_length=20,
        choices=STAFF_ROLES,
        verbose_name='Rol',
        help_text='Función que desempeña en el equipo'
    )
    
    # Estado y metadata
    is_active = models.BooleanField(
        default=True,
        verbose_name='Activo',
        help_text='¿Está actualmente trabajando con este equipo?'
    )
    notes = models.TextField(
        blank=True,
        verbose_name='Notas',
        help_text='Notas específicas sobre este rol'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creado')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Actualizado')

    class Meta:
        ordering = ['team', 'role', 'person__last_name', 'person__first_name']
        verbose_name = 'Rol de Staff'
        verbose_name_plural = 'Roles de Staff'
        indexes = [
            models.Index(fields=['team', 'is_active']),
            models.Index(fields=['person', 'is_active']),
            models.Index(fields=['role']),
        ]
        # Evitar duplicados de persona-equipo-rol activos
        constraints = [
            models.UniqueConstraint(
                fields=['person', 'team', 'role'],
                name='unique_active_staff_role',
                condition=models.Q(is_active=True)
            )
        ]

    def __str__(self):
        return f"{self.person.full_name} - {self.get_role_display()} ({self.team.name})"
    
    @property
    def display_role(self):
        """Devuelve el rol en formato legible"""
        return self.get_role_display()