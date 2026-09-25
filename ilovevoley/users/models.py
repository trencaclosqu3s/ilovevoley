from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
import secrets


class User(AbstractUser):
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    is_approved = models.BooleanField(
        default=False,
        help_text='Indica si el usuario ha sido aprobado por un administrador para acceder al contenido.'
    )
    parent_info = models.TextField(
        blank=True,
        verbose_name='Información Familiar',
        help_text='Indica de qué niño/a eres padre/familiar (ej: "papá de Juanito de Infantil")'
    )
    preferred_categories = models.ManyToManyField(
        'core.Category',
        blank=True,
        related_name='subscribed_users',
        verbose_name='Categorías de Interés',
        help_text='Categorías de contenido que deseas ver'
    )
    
    
    # Calendar subscription token (for .ics feed)
    calendar_token = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        verbose_name='Token de Suscripción al Calendario',
        help_text='Token único para suscribirse al calendario de partidos vía .ics'
    )
    
    # Relación con fichas de hijos (para padres)
    children = models.ManyToManyField(
        'rosters.Person',
        blank=True,
        related_name='parents',
        verbose_name='Hijos',
        help_text='Fichas de los hijos que puedes editar'
    )

    def __str__(self):
        return self.username

    def save(self, *args, **kwargs):
        # Sanear avatar automáticamente a nivel de modelo ante cualquier nueva subida
        if self.avatar and not getattr(self.avatar, '_committed', True):
            from ilovevoley.videos.utils import sanitize_image
            self.avatar = sanitize_image(self.avatar, max_size=1024)
        super().save(*args, **kwargs)
    
    def get_or_create_calendar_token(self):
        """Genera un token de calendario si no existe y lo retorna"""
        if not self.calendar_token:
            self.calendar_token = secrets.token_urlsafe(32)
            self.save(update_fields=['calendar_token'])
        return self.calendar_token
    
    
    def can_edit_person(self, person):
        """Verifica si el usuario puede editar una ficha específica"""
        # El propio usuario puede editar su ficha si está vinculada
        if person.user == self:
            return True
        
        # Los padres pueden editar las fichas de sus hijos
        if person in self.children.all():
            return True
            
        # Los administradores pueden editar cualquier ficha
        if self.is_staff:
            return True
            
        return False


from ilovevoley.core.models import Organization


class Membership(models.Model):
    ROLES = [
        ('admin', 'Admin'),
        ('manager', 'Manager'),
        ('member', 'Miembro'),
    ]

    user         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='memberships')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='memberships')
    role         = models.CharField(max_length=20, choices=ROLES, default='member')
    is_approved  = models.BooleanField(default=False)
    joined_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'organization')
        verbose_name = 'Membresía'
        verbose_name_plural = 'Membresías'

    def __str__(self):
        return f'{self.user} @ {self.organization} ({self.role})'
