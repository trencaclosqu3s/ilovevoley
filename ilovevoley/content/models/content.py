import os
import re
import uuid

from django.conf import settings
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ilovevoley.core.models import Season
from ilovevoley.core.tenancy import OrganizationTenantQuerySet


def infer_season(match, when):
    """Temporada de un contenido: la del partido o, si no la hay, la de la fecha."""
    if match is not None:
        if match.league_id and match.league.season_id:
            return match.league.season
        if match.match_date:
            return Season.objects.for_date(match.match_date)
    return Season.objects.for_date(when)


def infer_category(match):
    """Categoría de un contenido: la de los equipos del partido o la de su liga.

    Un vídeo tiene una sola categoría, así que se prioriza la del equipo local,
    después la del visitante y, si ninguna la tiene, la primera de la liga.
    """
    if match is None:
        return None
    for team in (match.home_team, match.away_team):
        if team is not None and team.category_id:
            return team.category
    if match.league_id:
        return match.league.categories.first()
    return None


class Video(models.Model):
    title = models.CharField(max_length=200)
    youtube_url = models.URLField()
    description = models.TextField(blank=True)
    category = models.ForeignKey('core.Category', on_delete=models.CASCADE, null=True, blank=True)
    match = models.ForeignKey('competitions.Match', on_delete=models.SET_NULL, null=True, blank=True, related_name='videos')
    season = models.ForeignKey(
        'core.Season',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='videos',
        verbose_name=_('Temporada'),
        help_text=_('Temporada a la que pertenece el vídeo'),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    organization = models.ForeignKey(
        'core.Organization',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='videos',
        verbose_name=_('Organización'),
    )
    set_number = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        verbose_name=_('Set'),
        help_text=_('Número de set al que pertenece (opcional, solo para vídeos de partido)'),
    )

    objects = OrganizationTenantQuerySet.as_manager()

    class Meta:
        db_table = 'videos_video'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['match', 'set_number'], name='video_match_set_idx'),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Inferir la temporada si no se especifica: del partido o de la fecha.
        if self.season_id is None:
            self.season = infer_season(
                self.match if self.match_id else None,
                self.created_at or timezone.now(),
            )
            update_fields = kwargs.get('update_fields')
            if update_fields is not None:
                kwargs['update_fields'] = set(update_fields) | {'season'}
        # Heredar la categoría del partido si no se especifica: si no, el vídeo
        # queda sin categoría y lo ocultan los filtros por categorías preferidas.
        if self.category_id is None and self.match_id:
            category = infer_category(self.match)
            if category is not None:
                self.category = category
                update_fields = kwargs.get('update_fields')
                if update_fields is not None:
                    kwargs['update_fields'] = set(update_fields) | {'category'}
        # Sin partido no hay set: el spec exige que quede NULL.
        if self.match_id is None and self.set_number is not None:
            self.set_number = None
            update_fields = kwargs.get('update_fields')
            if update_fields is not None:
                kwargs['update_fields'] = set(update_fields) | {'set_number'}
        super().save(*args, **kwargs)

    def get_video_id(self):
        """Extrae el ID de YouTube de la URL, o None si no se reconoce."""
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)',
            r'youtube\.com\/embed\/([^&\n?#]+)',
            r'youtube\.com\/live\/([^&\n?#]+)',  # livestreams
        ]
        for pattern in patterns:
            match = re.search(pattern, self.youtube_url)
            if match:
                return match.group(1)
        return None

    def get_embed_url(self):
        """Convierte la URL de YouTube en URL de embed con privacidad mejorada."""
        video_id = self.get_video_id()
        if video_id:
            # rel=0: sin vídeos relacionados; modestbranding=1; fs=1; enablejsapi=0
            return f'https://www.youtube-nocookie.com/embed/{video_id}?rel=0&modestbranding=1&fs=1&enablejsapi=0'
        return self.youtube_url

    def get_thumbnail_url(self):
        """Miniatura pública de YouTube para la portada del reproductor."""
        video_id = self.get_video_id()
        if video_id:
            return f'https://i.ytimg.com/vi/{video_id}/hqdefault.jpg'
        return None

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
        db_table = 'videos_comment'
        ordering = ['created_at']

    def __str__(self):
        return f'{self.user.username} - {self.content[:50]}...'


def image_upload_path(instance, filename):
    """Genera ruta de subida para imágenes organizadas por año y mes con identificador UUID"""
    from ilovevoley.videos.utils import build_uuid_upload_path
    now = timezone.now()
    return build_uuid_upload_path(f'images/{now.year}/{now.month:02d}', filename)


class Image(models.Model):
    MODERATION_STATUS = [
        ('pending', _('Pendiente de Moderación')),
        ('approved', _('Aprobada')),
        ('rejected', _('Rechazada')),
    ]

    IMAGE_TYPES = [
        ('match', _('Partido')),
        ('celebration', _('Celebración')),
        ('training', _('Entrenamiento')),
        ('team_photo', _('Foto de Equipo')),
        ('facilities', _('Instalaciones')),
        ('other', _('Otro')),
    ]

    image = models.ImageField(
        upload_to=image_upload_path,
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp', 'heic', 'heif'])],
        help_text=_('Formatos permitidos: JPG, PNG, WebP, HEIC. Tamaño máximo: 10MB')
    )
    title = models.CharField(max_length=200, help_text=_('Título descriptivo de la imagen'))
    description = models.TextField(blank=True, help_text=_('Descripción opcional'))

    # Campos para tracking de conversión de formato
    original_format = models.CharField(
        max_length=10,
        blank=True,
        help_text=_('Formato original del archivo (ej: heic, jpg)')
    )
    was_converted = models.BooleanField(
        default=False,
        help_text=_('Indica si la imagen fue convertida desde otro formato')
    )

    # Miniaturas derivadas (WebP/AVIF) para galerías responsivas
    thumbnail_small = models.ImageField(
        upload_to='image_thumbnails/',
        blank=True,
        null=True,
        editable=False,
        verbose_name=_('Miniatura 400px WebP'),
    )
    thumbnail_large = models.ImageField(
        upload_to='image_thumbnails/',
        blank=True,
        null=True,
        editable=False,
        verbose_name=_('Miniatura 1600px WebP'),
    )
    thumbnail_small_avif = models.ImageField(
        upload_to='image_thumbnails/',
        blank=True,
        null=True,
        editable=False,
        verbose_name=_('Miniatura 400px AVIF'),
    )
    thumbnail_large_avif = models.ImageField(
        upload_to='image_thumbnails/',
        blank=True,
        null=True,
        editable=False,
        verbose_name=_('Miniatura 1600px AVIF'),
    )

    # Tipo y etiquetas
    image_type = models.CharField(
        max_length=20,
        choices=IMAGE_TYPES,
        default='other',
        help_text=_('Tipo de imagen')
    )
    tags = models.CharField(
        max_length=500,
        blank=True,
        help_text=_('Etiquetas separadas por comas (ej: gol, victoria, senior)')
    )
    auto_tags = models.JSONField(
        default=list,
        blank=True,
        help_text=_('Etiquetas detectadas automáticamente por Vision API')
    )

    # Relaciones
    match = models.ForeignKey(
        'competitions.Match',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='images',
        help_text=_('Partido al que pertenece la imagen (opcional)')
    )
    album_group_id = models.UUIDField(
        null=True,
        blank=True,
        help_text=_('ID de grupo para agrupar imágenes en un álbum sin partido vinculado')
    )
    album_name = models.CharField(
        max_length=200,
        blank=True,
        help_text=_('Nombre del álbum cuando las imágenes están agrupadas sin partido')
    )
    categories = models.ManyToManyField(
        'core.Category',
        blank=True,
        related_name='images',
        db_table='videos_image_categories',
        help_text=_('Categorías asociadas a la imagen. Se asigna automáticamente desde el partido o manualmente')
    )
    persons = models.ManyToManyField(
        'rosters.Person',
        blank=True,
        related_name='tagged_images',
        db_table='videos_image_persons',
        verbose_name=_('Deportistas etiquetados'),
        help_text=_('Personas que aparecen en la imagen'),
    )
    season = models.ForeignKey(
        'core.Season',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='images',
        verbose_name=_('Temporada'),
        help_text=_('Temporada a la que pertenece la imagen'),
    )
    set_number = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        verbose_name=_('Set'),
        help_text=_('Número de set al que pertenece la imagen (opcional, solo si hay partido)'),
    )

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
        help_text=_('Estado de moderación')
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
        help_text=_('Notas internas de moderación')
    )

    # Google Vision API (opcional)
    vision_api_checked = models.BooleanField(default=False)
    vision_api_safe = models.BooleanField(default=True)
    vision_api_details = models.JSONField(default=dict, blank=True)

    organization = models.ForeignKey(
        'core.Organization',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='images',
        verbose_name=_('Organización'),
    )

    objects = OrganizationTenantQuerySet.as_manager()

    class Meta:
        db_table = 'videos_image'
        ordering = ['-upload_date']
        verbose_name = _('Imagen')
        verbose_name_plural = _('Imágenes')
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['match']),
            models.Index(fields=['album_group_id']),
            models.Index(fields=['upload_date']),
            models.Index(fields=['image_type']),
            models.Index(fields=['organization', 'status', '-upload_date'], name='img_org_status_date_idx'),
            models.Index(fields=['organization', 'match', 'status'], name='img_org_match_status_idx'),
            models.Index(fields=['organization', 'album_group_id', 'status'], name='img_org_album_status_idx'),
            models.Index(fields=['match', 'set_number'], name='img_match_set_idx'),
        ]

    def __str__(self):
        if self.match:
            return f'{self.title} - {self.match}'
        return f'{self.title} ({self.get_image_type_display()})'

    def save(self, *args, **kwargs):
        # Determinar si es una creación nueva
        is_new = self.pk is None
        changed = set()

        # Sanear imagen automáticamente a nivel de modelo ante cualquier nueva subida
        from ilovevoley.videos.utils import sanitize_model_image_field
        original_ext = getattr(self.image, 'name', '') if self.image else ''
        sanitized = sanitize_model_image_field(self, 'image', max_size=2560)
        if sanitized:
            if not self.original_format and original_ext:
                self.original_format = os.path.splitext(original_ext)[1].lower().lstrip('.')
                changed.add('original_format')
            if not self.was_converted and self.original_format not in ['jpg', 'jpeg']:
                self.was_converted = True
                changed.add('was_converted')

        # Auto-asignar temporada si no se especifica: del partido o de la fecha
        if self.season_id is None:
            self.season = infer_season(self.match if self.match_id else None, timezone.now())
            changed.add('season')

        # Si es una imagen de partido pero no se especificó el tipo, asignarlo
        if self.match_id and self.image_type == 'other':
            self.image_type = 'match'
            changed.add('image_type')

        # Sin partido no hay set: el spec exige que quede NULL.
        if self.match_id is None and self.set_number is not None:
            self.set_number = None
            changed.add('set_number')

        update_fields = kwargs.get('update_fields')
        if update_fields is not None and changed:
            kwargs['update_fields'] = set(update_fields) | changed

        super().save(*args, **kwargs)

        # Después de guardar, asignar categorías desde el partido si es nueva y no tiene categorías
        if is_new and self.match and not self.categories.exists():
            # Agregar todas las categorías de la liga
            if self.match.league:
                self.categories.add(*self.match.league.categories.all())
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
        """URL de la miniatura 400px WebP o, si no existe, la imagen original."""
        return self._variant_url(self.thumbnail_small) or self._original_url

    @property
    def thumbnail_srcset(self):
        """srcset WebP (400w/1600w) para el atributo de la etiqueta <img>."""
        return self._build_srcset(
            (self.thumbnail_small, 400),
            (self.thumbnail_large, 1600),
        )

    @property
    def thumbnail_srcset_avif(self):
        """srcset AVIF (400w/1600w), vacío si no se generaron variantes AVIF."""
        return self._build_srcset(
            (self.thumbnail_small_avif, 400),
            (self.thumbnail_large_avif, 1600),
        )

    @property
    def _original_url(self):
        return self.image.url if self.image else None

    @staticmethod
    def _variant_url(field):
        if field and field.name:
            try:
                return field.url
            except ValueError:
                return None
        return None

    def _build_srcset(self, *variants):
        parts = []
        for field, width in variants:
            url = self._variant_url(field)
            if url:
                parts.append(f'{url} {width}w')
        return ', '.join(parts)

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


class ImageFavorite(models.Model):
    """Un "me gusta" de una foto: un registro por usuario y foto.

    El contador de favoritas de cada foto y el top del partido se derivan de
    estas filas, así que el par (usuario, foto) es único a nivel de BD.
    """

    image = models.ForeignKey(
        Image,
        on_delete=models.CASCADE,
        related_name='favorites',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='favorite_images',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'videos_image_favorite'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'image'],
                name='unique_image_favorite_per_user',
            ),
        ]
        indexes = [
            models.Index(fields=['image']),
            models.Index(fields=['user', '-created_at'], name='fav_user_date_idx'),
        ]

    def __str__(self):
        return f'{self.user} ♥ {self.image_id}'


class ImageRemovalRequest(models.Model):
    """Petición de un deportista o su familia para retirar una foto etiquetada.

    La resuelve un administrador desde el panel de moderación, eliminando la
    imagen o descartando la petición. Se conserva el registro aunque la imagen
    se borre, para dejar rastro de la solicitud.
    """

    STATUS = [
        ('pending', _('Pendiente')),
        ('removed', _('Foto eliminada')),
        ('dismissed', _('Descartada')),
    ]

    organization = models.ForeignKey(
        'core.Organization',
        on_delete=models.PROTECT,
        related_name='image_removal_requests',
        verbose_name=_('Organización'),
    )
    image = models.ForeignKey(
        Image,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='removal_requests',
        verbose_name=_('Imagen'),
    )
    image_title = models.CharField(max_length=200, verbose_name=_('Título de la imagen'))
    person = models.ForeignKey(
        'rosters.Person',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='image_removal_requests',
        verbose_name=_('Deportista'),
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='image_removal_requests',
        verbose_name=_('Solicitada por'),
    )
    reason = models.TextField(
        max_length=500,
        blank=True,
        verbose_name=_('Motivo'),
        help_text=_('Motivo opcional de la solicitud'),
    )
    status = models.CharField(
        max_length=20, choices=STATUS, default='pending', verbose_name=_('Estado'),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Creada'))
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Resuelta'))
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_image_removal_requests',
        verbose_name=_('Resuelta por'),
    )

    class Meta:
        db_table = 'videos_image_removal_request'
        ordering = ['-created_at']
        verbose_name = _('Solicitud de retirada de imagen')
        verbose_name_plural = _('Solicitudes de retirada de imágenes')
        constraints = [
            models.UniqueConstraint(
                fields=['image'],
                condition=models.Q(status='pending'),
                name='unique_pending_image_removal',
            ),
        ]
        indexes = [
            models.Index(fields=['organization', 'status', '-created_at'], name='img_rm_org_status_idx'),
        ]

    def __str__(self):
        return f'{self.image_title} ({self.get_status_display()})'
