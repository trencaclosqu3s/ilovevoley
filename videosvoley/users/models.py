from django.contrib.auth.models import AbstractUser
from django.db import models


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
        'videos.Category',
        blank=True,
        related_name='subscribed_users',
        verbose_name='Categorías de Interés',
        help_text='Categorías de contenido que deseas ver'
    )
    
    # Google Calendar Sync fields
    calendar_sync_enabled = models.BooleanField(
        default=False,
        verbose_name='Sincronizar con Google Calendar',
        help_text='Sincronizar automáticamente los partidos de tus categorías preferidas con Google Calendar'
    )
    calendar_last_sync = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Última Sincronización',
        help_text='Fecha y hora de la última sincronización con Google Calendar'
    )
    google_calendar_id = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='ID del Calendar de Google',
        help_text='ID del calendar específico donde sincronizar eventos (opcional, usa calendar principal si está vacío)'
    )

    def __str__(self):
        return self.username
    
    def has_google_calendar_permissions(self):
        """Verifica si el usuario tiene permisos para acceder a Google Calendar"""
        try:
            from allauth.socialaccount.models import SocialToken
            google_account = self.socialaccount_set.filter(provider='google').first()
            if not google_account:
                return False
            
            # Verificar si tiene token válido
            token = SocialToken.objects.filter(
                account=google_account,
                app__provider='google'
            ).first()
            
            return token is not None
        except ImportError:
            return False
    
    def can_sync_calendar(self):
        """Verifica si el usuario puede sincronizar con calendar"""
        return (
            self.calendar_sync_enabled and 
            self.has_google_calendar_permissions() and
            self.preferred_categories.exists()
        )
