from urllib.parse import urlparse

from django.db import models
from django.core.validators import RegexValidator
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

_hex_color_validator = RegexValidator(r'^#[0-9a-fA-F]{6}$', 'Introduce un color hexadecimal válido (ej: #9B7FBF)')


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'videos_category'
        ordering = ['name']
        verbose_name = 'Categoría'
        verbose_name_plural = 'Categorías'

    def __str__(self):
        return self.name


class Organization(models.Model):
    slug            = models.CharField(max_length=50, unique=True)
    name            = models.CharField(max_length=100)
    logo            = models.ImageField(upload_to='organizations/logos/', null=True, blank=True)
    primary_color   = models.CharField(max_length=7, default='#9B7FBF', validators=[_hex_color_validator])
    secondary_color = models.CharField(max_length=7, default='#7B5FA0', blank=True, validators=[_hex_color_validator])
    instagram_url   = models.URLField(blank=True, help_text='URL del perfil de Instagram del club')
    club_team_names = models.JSONField(default=dict, help_text='{"Senior": "SANT JOSEP", "Juvenil": "SANT JOSEP B"}')
    club            = models.ForeignKey(
        'teams.Club',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='organizations',
        help_text='Club federativo vinculado (opcional; null p.ej. para selecciones)',
    )
    is_active       = models.BooleanField(default=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Organización'
        verbose_name_plural = 'Organizaciones'
        ordering = ['name']

    def __str__(self):
        return self.name

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
