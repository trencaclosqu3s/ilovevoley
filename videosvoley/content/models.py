from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import FileExtensionValidator
from django.contrib.auth import get_user_model
import re
import os
import uuid

User = get_user_model()


class Category(models.Model):
    """Categorías para organizar contenido (videos, imágenes)"""
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
    """Modelo para videos de YouTube"""
    title = models.CharField(max_length=200)
    youtube_url = models.URLField()
    description = models.TextField(blank=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, null=True, blank=True)
    # Foreign key temporal - se actualizará cuando migremos Match
    match = models.ForeignKey('videos.Match', on_delete=models.SET_NULL, null=True, blank=True, related_name='content_videos')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='content_videos')

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Vídeo'
        verbose_name_plural = 'Vídeos'

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
    """Comentarios en videos"""
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='content_comments')
    content = models.TextField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Comentario'
        verbose_name_plural = 'Comentarios'

    def __str__(self):
        return f'{self.user.username} - {self.content[:50]}...'


def image_upload_path(instance, filename):
    """Genera ruta de subida para imágenes organizadas por año y mes"""
    year = timezone.now().year
    month = timezone.now().month
    # Mantener extensión original pero limpiar el nombre
    name, ext = os.path.splitext(filename)
    clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    return f'images/{year}/{month:02d}/{clean_name}{ext}'


class Image(models.Model):
    """Modelo para gestión de imágenes con moderación"""
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
    # Foreign key temporal - se actualizará cuando migremos Match
    match = models.ForeignKey(
        'videos.Match', 
        on_delete=models.CASCADE, 
        null=True,
        blank=True,
        related_name='content_images',
        help_text='Partido al que pertenece la imagen (opcional)'
    )
    # Campos para álbumes sin partido (retrocompatibles)
    album_group_id = models.UUIDField(
        null=True,
        blank=True,
        help_text='ID de grupo para agrupar imágenes en un álbum sin partido vinculado'
    )
    album_name = models.CharField(
        max_length=200,
        blank=True,
        help_text='Nombre del álbum cuando las imágenes están agrupadas sin partido'
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
        related_name='content_uploaded_images'
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
        related_name='content_moderated_images'
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
            models.Index(fields=['album_group_id']),
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