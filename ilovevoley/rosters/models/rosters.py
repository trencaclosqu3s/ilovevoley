import uuid

from django.conf import settings
from django.db import models

from ilovevoley.core.tenancy import OrganizationTenantQuerySet, PersonRoleTenantQuerySet


def person_photo_upload_path(instance, filename):
    """Generar un path aleatorio e inextensible para la foto de una persona."""
    return f'people/{uuid.uuid4().hex}.jpg'


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
    
    # Pertenencia a la organización (tenant). Determina la visibilidad y
    # edición de la ficha. Queda nula en fichas heredadas que no se pudieron
    # resolver de forma inequívoca (quedan ocultas en todos los tenants).
    organization = models.ForeignKey(
        'core.Organization',
        on_delete=models.PROTECT,
        related_name='people',
        null=True,
        blank=True,
        verbose_name='Organización',
        help_text='Club/organización al que pertenece la ficha'
    )

    # Vinculación con usuario de la plataforma
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
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

    objects = OrganizationTenantQuerySet.as_manager()

    class Meta:
        db_table = 'videos_person'
        ordering = ['last_name', 'first_name']
        verbose_name = 'Ficha'
        verbose_name_plural = 'Fichas'
        indexes = [
            models.Index(fields=['last_name', 'first_name']),
            models.Index(fields=['is_active']),
            models.Index(fields=['created_at']),
        ]
        # Evitar duplicados exactos dentro de cada organización. La identidad
        # es por tenant, de modo que la misma persona pueda tener ficha en dos
        # clubes. Las fichas heredadas sin organización (organization NULL)
        # forman su propio grupo (nulls_distinct=False), conservando la
        # deduplicación global entre ellas.
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'first_name', 'last_name', 'birth_date'],
                name='unique_person_identity',
                condition=models.Q(birth_date__isnull=False),
                nulls_distinct=False,
            )
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def save(self, *args, **kwargs):
        # Sanear foto automáticamente a nivel de modelo ante cualquier nueva subida
        from ilovevoley.videos.utils import sanitize_model_image_field
        sanitize_model_image_field(self, 'photo', max_size=2048)
        super().save(*args, **kwargs)

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
        from django.apps import apps
        from django.db.models import Q
        Team = apps.get_model('teams', 'Team')
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
        'teams.Team',
        on_delete=models.CASCADE,
        related_name='player_roles',
        verbose_name='Equipo'
    )
    season = models.ForeignKey(
        'core.Season',
        on_delete=models.PROTECT,
        related_name='player_roles',
        verbose_name='Temporada',
        help_text='Temporada en la que el jugador pertenece al equipo',
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

    objects = PersonRoleTenantQuerySet.as_manager()

    class Meta:
        db_table = 'videos_playerrole'
        ordering = ['team', 'jersey_number', 'person__last_name', 'person__first_name']
        verbose_name = 'Rol de Jugador'
        verbose_name_plural = 'Roles de Jugador'
        indexes = [
            models.Index(fields=['team', 'is_active']),
            models.Index(fields=['person', 'is_active']),
            models.Index(fields=['jersey_number']),
            models.Index(fields=['position']),
        ]
        # Evitar duplicados de persona-equipo activos dentro de una temporada
        constraints = [
            models.UniqueConstraint(
                fields=['person', 'team', 'season'],
                name='unique_active_player_role',
                condition=models.Q(is_active=True)
            ),
            # Evitar números de dorsal duplicados en el mismo equipo y temporada
            models.UniqueConstraint(
                fields=['team', 'season', 'jersey_number'],
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
        'teams.Team',
        on_delete=models.CASCADE,
        related_name='staff_roles',
        verbose_name='Equipo'
    )
    season = models.ForeignKey(
        'core.Season',
        on_delete=models.PROTECT,
        related_name='staff_roles',
        verbose_name='Temporada',
        help_text='Temporada en la que la persona desempeña el rol',
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

    objects = PersonRoleTenantQuerySet.as_manager()

    class Meta:
        db_table = 'videos_staffrole'
        ordering = ['team', 'role', 'person__last_name', 'person__first_name']
        verbose_name = 'Rol de Staff'
        verbose_name_plural = 'Roles de Staff'
        indexes = [
            models.Index(fields=['team', 'is_active']),
            models.Index(fields=['person', 'is_active']),
            models.Index(fields=['role']),
        ]
        # Evitar duplicados de persona-equipo-rol activos dentro de una temporada
        constraints = [
            models.UniqueConstraint(
                fields=['person', 'team', 'role', 'season'],
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
