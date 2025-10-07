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

    def __str__(self):
        return self.username
