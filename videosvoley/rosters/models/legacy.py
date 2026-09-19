import os
import re

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone


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
        'teams.Team', 
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
        db_table = 'videos_player'
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
        'teams.Team', 
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
        db_table = 'videos_staff'
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
