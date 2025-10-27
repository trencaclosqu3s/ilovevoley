from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator


def person_photo_upload_path(instance, filename):
    """Genera la ruta de subida para fotos de personas"""
    return f'people/{instance.id}/{filename}'


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
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Usuario Vinculado',
        help_text='Usuario de la plataforma asociado (opcional)',
        related_name='rosters_person'
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
                name='unique_rosters_person_identity',
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
        # Foreign keys temporales - se actualizarán cuando se cree la app teams
        from videosvoley.videos.models import Team
        player_teams = Team.objects.filter(player_roles__person=self, player_roles__is_active=True)
        staff_teams = Team.objects.filter(staff_roles__person=self, staff_roles__is_active=True)
        return Team.objects.filter(Q(id__in=player_teams) | Q(id__in=staff_teams)).distinct()

    def get_roles_summary(self):
        """Resumen de todos los roles de la persona"""
        player_roles = self.get_player_roles()
        staff_roles = self.get_staff_roles()
        
        return {
            'player_roles': [
                {
                    'team': role.team.name,
                    'position': role.display_position,
                    'jersey_number': role.jersey_number,
                }
                for role in player_roles
            ],
            'staff_roles': [
                {
                    'team': role.team.name,
                    'role': role.display_role,
                }
                for role in staff_roles
            ],
            'total_teams': len(set([role.team.id for role in player_roles] + [role.team.id for role in staff_roles]))
        }


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
    # Foreign key temporal - se actualizará cuando se cree la app teams
    team = models.ForeignKey(
        'videos.Team',
        on_delete=models.CASCADE,
        related_name='rosters_player_roles',
        verbose_name='Equipo'
    )
    
    # Información específica del rol de jugador
    jersey_number = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(99)],
        verbose_name='Número de Dorsal',
        help_text='Número de la camiseta (1-99)'
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
                name='unique_rosters_active_player_role',
                condition=models.Q(is_active=True)
            ),
            # Evitar números de dorsal duplicados en el mismo equipo
            models.UniqueConstraint(
                fields=['team', 'jersey_number'],
                name='unique_rosters_jersey_number_per_team',
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

    @property
    def team_category(self):
        """Categoría del equipo"""
        return self.team.category.name if self.team.category else "Sin categoría"

    def clean(self):
        """Validaciones personalizadas"""
        from django.core.exceptions import ValidationError
        
        # Validar que el número de dorsal no esté duplicado en el equipo
        if self.jersey_number and self.team_id:
            existing = PlayerRole.objects.filter(
                team=self.team,
                jersey_number=self.jersey_number,
                is_active=True
            ).exclude(pk=self.pk)
            if existing.exists():
                raise ValidationError(f'El número {self.jersey_number} ya está en uso en {self.team.name}')


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
    # Foreign key temporal - se actualizará cuando se cree la app teams
    team = models.ForeignKey(
        'videos.Team',
        on_delete=models.CASCADE,
        related_name='rosters_staff_roles',
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
                name='unique_rosters_active_staff_role',
                condition=models.Q(is_active=True)
            )
        ]

    def __str__(self):
        return f"{self.person.full_name} - {self.get_role_display()} ({self.team.name})"
    
    @property
    def display_role(self):
        """Devuelve el rol en formato legible"""
        return self.get_role_display()

    @property
    def team_category(self):
        """Categoría del equipo"""
        return self.team.category.name if self.team.category else "Sin categoría"


class PersonManager(models.Manager):
    """Manager personalizado para personas"""
    
    def active(self):
        """Personas activas"""
        return self.filter(is_active=True)
    
    def with_roles(self):
        """Personas que tienen roles (jugador o staff)"""
        from django.db.models import Q
        return self.filter(
            Q(player_roles__isnull=False) | Q(staff_roles__isnull=False)
        ).distinct()
    
    def players_only(self):
        """Solo personas que son jugadores"""
        return self.filter(player_roles__isnull=False).distinct()
    
    def staff_only(self):
        """Solo personas que son staff"""
        return self.filter(staff_roles__isnull=False).distinct()
    
    def by_team(self, team):
        """Personas de un equipo específico"""
        from django.db.models import Q
        return self.filter(
            Q(player_roles__team=team) | Q(staff_roles__team=team)
        ).distinct()
    
    def by_age_range(self, min_age=None, max_age=None):
        """Personas por rango de edad"""
        from datetime import date, timedelta
        
        queryset = self.all()
        
        if min_age is not None:
            max_birth_date = date.today() - timedelta(days=min_age * 365)
            queryset = queryset.filter(birth_date__lte=max_birth_date)
        
        if max_age is not None:
            min_birth_date = date.today() - timedelta(days=(max_age + 1) * 365)
            queryset = queryset.filter(birth_date__gte=min_birth_date)
        
        return queryset


class PlayerRoleManager(models.Manager):
    """Manager personalizado para roles de jugador"""
    
    def active(self):
        """Roles activos"""
        return self.filter(is_active=True)
    
    def by_team(self, team):
        """Roles de un equipo específico"""
        return self.filter(team=team, is_active=True)
    
    def by_position(self, position):
        """Roles por posición"""
        return self.filter(position=position, is_active=True)
    
    def with_jersey_numbers(self):
        """Roles que tienen número de dorsal"""
        return self.filter(jersey_number__isnull=False, is_active=True)


class StaffRoleManager(models.Manager):
    """Manager personalizado para roles de staff"""
    
    def active(self):
        """Roles activos"""
        return self.filter(is_active=True)
    
    def by_team(self, team):
        """Roles de un equipo específico"""
        return self.filter(team=team, is_active=True)
    
    def by_role(self, role):
        """Roles por tipo de staff"""
        return self.filter(role=role, is_active=True)
    
    def coaches(self):
        """Solo entrenadores"""
        return self.filter(
            role__in=['head_coach', 'assistant_coach'],
            is_active=True
        )