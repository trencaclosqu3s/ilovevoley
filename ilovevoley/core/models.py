import datetime
import re
from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.core.validators import RegexValidator
from django.db.models import Q
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

_hex_color_validator = RegexValidator(r'^#[0-9a-fA-F]{6}$', _('Introduce un color hexadecimal válido (ej: #9B7FBF)'))

# Una temporada empieza el 1 de septiembre y termina el 31 de agosto.
SEASON_START_MONTH = 9
_INVALID_SEASON_MSG = _('Formato de temporada no válido (ej: 2025-26).')

# Ramas/géneros soportados. Vacío = sin especificar.
GENDER_MALE = 'male'
GENDER_FEMALE = 'female'
GENDER_MIXED = 'mixed'
GENDER_CHOICES = [
    ('', _('Sin especificar')),
    (GENDER_MALE, _('Masculino')),
    (GENDER_FEMALE, _('Femenino')),
    (GENDER_MIXED, _('Mixto')),
]


def infer_gender_from_name(name):
    """Infiere el género desde un nombre libre de categoría o liga.

    Devuelve uno de GENDER_CHOICES o ``''`` si no se reconoce. No se detectan
    iniciales (M/F) por el riesgo de falsos positivos.
    """
    if not name:
        return ''
    lowered = name.lower()
    if 'femen' in lowered:
        return GENDER_FEMALE
    if 'mascul' in lowered:
        return GENDER_MALE
    if 'mixt' in lowered:
        return GENDER_MIXED
    return ''


def normalize_season_name(raw):
    """Normaliza una temporada a formato canónico 'YYYY-YY'.

    Acepta '2025-26', '2025-2026' y '2025/26'. Devuelve None para valores
    vacíos, None o no reconocidos (p.ej. 'temp').
    """
    if raw is None:
        return None
    match = re.match(r'^(\d{4})\s*[-/ ]\s*(\d{2}|\d{4})$', str(raw).strip())
    if not match:
        return None
    start = int(match.group(1))
    end_raw = match.group(2)
    if len(end_raw) == 4:
        end = int(end_raw)
    else:
        end = (start // 100) * 100 + int(end_raw)
        if end < start:
            end += 100
    if end != start + 1:
        return None
    return f'{start}-{end % 100:02d}'


def season_start_year_for_date(value):
    """Año de inicio de la temporada que contiene la fecha dada (corte 1 sept)."""
    if isinstance(value, datetime.datetime) and timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.year if value.month >= SEASON_START_MONTH else value.year - 1


class SeasonManager(models.Manager):
    """Manager de Season con resolución de la temporada activa."""

    def current(self):
        """Temporada activa; si no hay ninguna marcada, la más reciente."""
        return self.filter(is_current=True).first() or self.order_by('-start_year').first()

    def resolve(self, raw):
        """Normaliza un string y devuelve (creándola si hace falta) su Season."""
        name = normalize_season_name(raw)
        if not name:
            return None
        start_year = int(name.split('-')[0])
        season, _ = self.get_or_create(
            name=name,
            defaults={'start_year': start_year, 'end_year': start_year + 1},
        )
        return season

    def for_date(self, value):
        """Season correspondiente a una fecha (corte 1 septiembre)."""
        start_year = season_start_year_for_date(value)
        return self.resolve(f'{start_year}-{start_year + 1}')


class Season(models.Model):
    name = models.CharField(max_length=20, unique=True, help_text=_('Nombre canónico, ej: 2025-26'))
    start_year = models.IntegerField(help_text=_('Año de inicio, ej: 2025'))
    end_year = models.IntegerField(help_text=_('Año de fin, ej: 2026'))
    is_current = models.BooleanField(default=False, help_text=_('Temporada activa (solo puede haber una)'))
    created_at = models.DateTimeField(auto_now_add=True)

    objects = SeasonManager()

    class Meta:
        db_table = 'videos_season'
        ordering = ['-start_year']
        verbose_name = _('Temporada')
        verbose_name_plural = _('Temporadas')
        constraints = [
            models.UniqueConstraint(
                fields=['is_current'],
                condition=Q(is_current=True),
                name='unique_current_season',
            ),
        ]

    def __str__(self):
        return self.name

    def _normalize(self):
        """Normaliza el nombre y deriva el periodo. Lanza ValidationError si no es válido."""
        normalized = normalize_season_name(self.name)
        if not normalized:
            raise ValidationError({'name': _INVALID_SEASON_MSG})
        self.name = normalized
        self.start_year = int(normalized.split('-')[0])
        self.end_year = self.start_year + 1

    def clean(self):
        self._normalize()

    def save(self, *args, **kwargs):
        self._normalize()
        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            kwargs['update_fields'] = set(update_fields) | {'name', 'start_year', 'end_year'}
        if self.is_current:
            with transaction.atomic():
                Season.objects.select_for_update().filter(is_current=True).exclude(pk=self.pk).update(is_current=False)
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    gender = models.CharField(
        max_length=10,
        choices=GENDER_CHOICES,
        blank=True,
        default='',
        db_index=True,
        verbose_name=_('Género / Rama'),
        help_text=_('Vacío si la categoría es genérica (ej. "Senior").'),
    )

    class Meta:
        db_table = 'videos_category'
        ordering = ['name']
        verbose_name = _('Categoría')
        verbose_name_plural = _('Categorías')

    def __str__(self):
        return self.name


class Organization(models.Model):
    HOME_VIDEOS       = 'videos'
    HOME_IMAGES       = 'images'
    HOME_COMPETITIONS = 'competitions'
    HOME_CHOICES = [
        (HOME_VIDEOS, _('Vídeos')),
        (HOME_IMAGES, _('Imágenes')),
        (HOME_COMPETITIONS, _('Ligas y partidos')),
    ]
    HOME_URL_NAMES = {
        HOME_VIDEOS: 'content:video_list',
        HOME_IMAGES: 'content:image_gallery',
        HOME_COMPETITIONS: 'competitions:league_list',
    }

    slug            = models.CharField(max_length=50, unique=True)
    name            = models.CharField(max_length=100)
    logo            = models.ImageField(upload_to='organizations/logos/', null=True, blank=True)
    primary_color   = models.CharField(max_length=7, default='#9B7FBF', validators=[_hex_color_validator])
    secondary_color = models.CharField(max_length=7, default='#7B5FA0', blank=True, validators=[_hex_color_validator])
    gradient_color  = models.CharField(
        max_length=7, blank=True, validators=[_hex_color_validator],
        help_text=_('Color final del degradado de la cabecera del perfil. Vacío: usa el color secundario.'),
    )
    instagram_url   = models.URLField(blank=True, help_text=_('URL del perfil de Instagram del club'))
    default_home    = models.CharField(
        max_length=20,
        choices=HOME_CHOICES,
        default=HOME_VIDEOS,
        help_text=_('Sección a la que redirige la raíz del tenant.'),
    )
    club_team_names = models.JSONField(default=dict, help_text='{"Senior": "SANT JOSEP", "Juvenil": "SANT JOSEP B"}')
    club            = models.ForeignKey(
        'teams.Club',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='organizations',
        help_text=_('Club federativo vinculado (opcional; null p.ej. para selecciones)'),
    )
    is_active       = models.BooleanField(default=True)
    notify_match_changes = models.BooleanField(
        default=True,
        help_text=_('Recibir avisos de cambios federativos de los partidos de sus equipos'),
    )
    has_male_branch = models.BooleanField(
        default=True,
        verbose_name=_('Rama masculina activa'),
        help_text=_('Recibir avisos de partidos masculinos.'),
    )
    has_female_branch = models.BooleanField(
        default=False,
        verbose_name=_('Rama femenina activa'),
        help_text=_('Recibir avisos de partidos femeninos.'),
    )
    has_mixed_branch = models.BooleanField(
        default=False,
        verbose_name=_('Rama mixta activa'),
        help_text=_('Recibir avisos de partidos mixtos.'),
    )
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Organización')
        verbose_name_plural = _('Organizaciones')
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def home_url_name(self):
        """Nombre de URL de la homepage del tenant, con fallback a vídeos."""
        return self.HOME_URL_NAMES.get(
            self.default_home, self.HOME_URL_NAMES[self.HOME_VIDEOS]
        )

    @property
    def active_branches(self):
        """Ramas que compite la organización, según sus booleanos."""
        branches = set()
        if self.has_male_branch:
            branches.add(GENDER_MALE)
        if self.has_female_branch:
            branches.add(GENDER_FEMALE)
        if self.has_mixed_branch:
            branches.add(GENDER_MIXED)
        return branches

    @property
    def instagram_handle(self):
        if not self.instagram_url:
            return ''
        path = urlparse(self.instagram_url).path.strip('/')
        if not path:
            return ''
        handle = path.split('/')[0]
        return f'@{handle}' if handle else ''


@receiver(post_save, sender=Organization)
@receiver(post_delete, sender=Organization)
def invalidate_org_cache(sender, instance, **kwargs):
    from .tenant_utils import invalidate_organization_cache
    invalidate_organization_cache(instance.slug)
