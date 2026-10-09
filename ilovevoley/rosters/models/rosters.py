import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ilovevoley.core.tenancy import PersonRoleTenantQuerySet, PersonTenantQuerySet


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
        verbose_name=_('Nombre'),
        help_text=_('Nombre de la persona')
    )
    last_name = models.CharField(
        max_length=100, 
        verbose_name=_('Apellidos'),
        help_text=_('Apellidos de la persona')
    )
    birth_date = models.DateField(
        null=True, 
        blank=True, 
        verbose_name=_('Fecha de Nacimiento'),
        help_text=_('Fecha de nacimiento (opcional)')
    )
    birth_year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name=_('Año de Nacimiento'),
        help_text=_('Año de nacimiento; se rellena solo si hay fecha de nacimiento'),
    )
    photo = models.ImageField(
        upload_to=person_photo_upload_path,
        null=True,
        blank=True,
        verbose_name=_('Foto'),
        help_text=_('Foto de la persona (opcional)')
    )
    
    # Información de contacto
    email = models.EmailField(
        blank=True,
        verbose_name=_('Email'),
        help_text=_('Dirección de email (opcional)')
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name=_('Teléfono'),
        help_text=_('Número de teléfono (opcional)')
    )
    
    # Clubes que ven la ficha sin necesidad de rol (alta o adopción). Además,
    # una ficha es visible en el club donde tenga roles. El estado por club
    # (alta/baja) vive en PersonOrganization (#478).
    organizations = models.ManyToManyField(
        'core.Organization',
        through='PersonOrganization',
        related_name='people',
        blank=True,
        verbose_name=_('Organizaciones'),
        help_text=_('Clubes/organizaciones vinculados a la ficha'),
    )

    # Vinculación con usuario de la plataforma
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Usuario Vinculado'),
        help_text=_('Usuario de la plataforma asociado (opcional)')
    )
    
    # Notas y observaciones
    notes = models.TextField(
        blank=True,
        verbose_name=_('Notas'),
        help_text=_('Notas adicionales sobre la persona')
    )
    
    # Consentimiento de imagen dado por la familia (#122). Por defecto se
    # presupone uso interno: la galería solo la ven miembros aprobados del club.
    class ImageConsent(models.TextChoices):
        NONE = 'none', _('Sin consentimiento')
        INTERNAL_ONLY = 'internal_only', _('Solo uso interno del club')
        FULL_PUBLIC = 'full_public', _('Uso público')

    image_consent = models.CharField(
        max_length=20,
        choices=ImageConsent.choices,
        default=ImageConsent.INTERNAL_ONLY,
        verbose_name=_('Consentimiento de imagen'),
        help_text=_('Uso de la imagen autorizado por el deportista o su familia'),
    )
    image_consent_updated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Consentimiento actualizado'),
    )

    # Estado y metadata
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('Activo'),
        help_text=_('¿Está activo en el club?')
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Creado'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Actualizado'))

    objects = PersonTenantQuerySet.as_manager()

    class Meta:
        db_table = 'videos_person'
        ordering = ['last_name', 'first_name']
        verbose_name = _('Ficha')
        verbose_name_plural = _('Fichas')
        indexes = [
            models.Index(fields=['last_name', 'first_name']),
            models.Index(fields=['is_active']),
            models.Index(fields=['created_at']),
        ]
        # Identidad global: una persona es una persona en todos los clubes.
        # Con birth_year NULL (fichas sin año) no se aplica; se exigirá al
        # pasar a NOT NULL cuando estén rellenadas.
        constraints = [
            models.UniqueConstraint(
                fields=['first_name', 'last_name', 'birth_year'],
                name='unique_person_identity',
                violation_error_message=_('Ya existe una ficha con ese nombre, apellidos y año de nacimiento.'),
            )
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def save(self, *args, **kwargs):
        # Sanear foto automáticamente a nivel de modelo ante cualquier nueva subida
        from ilovevoley.videos.utils import sanitize_model_image_field
        sanitize_model_image_field(self, 'photo', max_size=2048)
        if self.birth_date:
            self.birth_year = self.birth_date.year
        # La fecha solo refleja decisiones reales: el valor por defecto de una
        # ficha nueva no cuenta como consentimiento recogido.
        previous = (
            Person._base_manager.filter(pk=self.pk).values_list('image_consent', flat=True).first()
            if self.pk else self.ImageConsent.INTERNAL_ONLY
        )
        if previous is not None and previous != self.image_consent:
            self.image_consent_updated_at = timezone.now()
            if kwargs.get('update_fields') is not None:
                kwargs['update_fields'] = {*kwargs['update_fields'], 'image_consent_updated_at'}
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
        return _('%(age)s años') % {'age': age} if age is not None else _('No especificada')
    
    @property
    def photo_preview(self):
        """Preview de la foto para el admin"""
        if self.photo:
            from django.utils.html import format_html
            return format_html('<img src="{}" width="50" height="50" style="object-fit: cover; border-radius: 4px;" />', self.photo.url)
        return _("Sin foto")
    
    @property
    def contact_info(self):
        """Información de contacto resumida"""
        contact_parts = []
        if self.email:
            contact_parts.append(self.email)
        if self.phone:
            contact_parts.append(self.phone)
        return " / ".join(contact_parts) or _("Sin contacto")
    
    def enroll(self, organization):
        """Da de alta (o reactiva) la pertenencia deportiva de la ficha a un club.

        `save()` del M2M sobre una fila existente es un no-op y no reactivaría
        una baja, de ahí este punto único de escritura (#478).
        """
        PersonOrganization.objects.update_or_create(
            person=self,
            organization=organization,
            defaults={'is_active': True, 'end_date': None},
        )

    def get_player_roles(self):
        """Obtiene todos los roles de jugador de esta persona"""
        return self.player_roles.filter(is_active=True).select_related('identity', 'identity__category')
    
    def get_staff_roles(self):
        """Obtiene todos los roles de staff de esta persona"""
        return self.staff_roles.filter(is_active=True).select_related('identity', 'identity__category')
    
    def get_active_identities(self):
        """Equipos (identidades) donde tiene roles activos."""
        from django.apps import apps
        from django.db.models import Q
        TeamIdentity = apps.get_model('teams', 'TeamIdentity')
        return TeamIdentity.objects.filter(
            Q(player_roles__person=self, player_roles__is_active=True)
            | Q(staff_roles__person=self, staff_roles__is_active=True)
        ).distinct()


class PlayerRole(models.Model):
    """
    Rol de jugador de una persona en un equipo específico.
    Una persona puede ser jugador en múltiples equipos.
    """
    POSITION_CHOICES = [
        ('setter', _('Colocador')),
        ('outside_hitter', _('Receptor')),
        ('middle_blocker', _('Central')),
        ('opposite', _('Opuesto')),
        ('libero', _('Líbero')),
    ]
    
    # Relaciones
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name='player_roles',
        verbose_name=_('Persona')
    )
    identity = models.ForeignKey(
        'teams.TeamIdentity',
        on_delete=models.PROTECT,
        related_name='player_roles',
        verbose_name=_('Equipo'),
    )
    season = models.ForeignKey(
        'core.Season',
        on_delete=models.PROTECT,
        related_name='player_roles',
        verbose_name=_('Temporada'),
        help_text=_('Temporada en la que el jugador pertenece al equipo'),
    )

    # Información específica del rol de jugador
    jersey_number = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name=_('Número de Dorsal'),
        help_text=_('Número de la camiseta (opcional)')
    )
    position = models.CharField(
        max_length=20,
        choices=POSITION_CHOICES,
        blank=True,
        verbose_name=_('Posición'),
        help_text=_('Posición preferida (opcional)')
    )
    
    # Estado y metadata
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('Activo'),
        help_text=_('¿Está actualmente jugando en este equipo?')
    )
    notes = models.TextField(
        blank=True,
        verbose_name=_('Notas'),
        help_text=_('Notas específicas sobre este rol')
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Creado'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Actualizado'))

    objects = PersonRoleTenantQuerySet.as_manager()

    class Meta:
        db_table = 'videos_playerrole'
        ordering = ['identity', 'jersey_number', 'person__last_name', 'person__first_name']
        verbose_name = _('Rol de Jugador')
        verbose_name_plural = _('Roles de Jugador')
        indexes = [
            models.Index(fields=['identity', 'is_active']),
            models.Index(fields=['person', 'is_active']),
            models.Index(fields=['jersey_number']),
            models.Index(fields=['position']),
        ]
        # Evitar duplicados de persona-equipo activos dentro de una temporada
        constraints = [
            models.UniqueConstraint(
                fields=['person', 'identity', 'season'],
                name='unique_active_player_role',
                condition=models.Q(is_active=True)
            ),
            # Evitar números de dorsal duplicados en el mismo equipo y temporada
            models.UniqueConstraint(
                fields=['identity', 'season', 'jersey_number'],
                name='unique_jersey_number_per_team',
                condition=models.Q(jersey_number__isnull=False, is_active=True)
            )
        ]

    def __str__(self):
        jersey_info = f" (#{self.jersey_number})" if self.jersey_number else ""
        return f"{self.person.full_name}{jersey_info} - {self.identity}"
    
    @property
    def display_position(self):
        """Devuelve la posición en formato legible"""
        return self.get_position_display() if self.position else _("Sin posición")


class StaffRole(models.Model):
    """
    Rol de staff de una persona en un equipo específico.
    Una persona puede tener roles de staff en múltiples equipos.
    """
    STAFF_ROLES = [
        ('head_coach', _('Entrenador/a')),
        ('assistant_coach', _('Segundo Entrenador/a')),
        ('delegate', _('Delegado/a')),
        ('other', _('Otro')),
    ]
    
    # Relaciones
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name='staff_roles',
        verbose_name=_('Persona')
    )
    identity = models.ForeignKey(
        'teams.TeamIdentity',
        on_delete=models.PROTECT,
        related_name='staff_roles',
        verbose_name=_('Equipo'),
    )
    season = models.ForeignKey(
        'core.Season',
        on_delete=models.PROTECT,
        related_name='staff_roles',
        verbose_name=_('Temporada'),
        help_text=_('Temporada en la que la persona desempeña el rol'),
    )

    # Información específica del rol de staff
    role = models.CharField(
        max_length=20,
        choices=STAFF_ROLES,
        verbose_name=_('Rol'),
        help_text=_('Función que desempeña en el equipo')
    )
    
    # Estado y metadata
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('Activo'),
        help_text=_('¿Está actualmente trabajando con este equipo?')
    )
    notes = models.TextField(
        blank=True,
        verbose_name=_('Notas'),
        help_text=_('Notas específicas sobre este rol')
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Creado'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Actualizado'))

    objects = PersonRoleTenantQuerySet.as_manager()

    class Meta:
        db_table = 'videos_staffrole'
        ordering = ['identity', 'role', 'person__last_name', 'person__first_name']
        verbose_name = _('Rol de Staff')
        verbose_name_plural = _('Roles de Staff')
        indexes = [
            models.Index(fields=['identity', 'is_active']),
            models.Index(fields=['person', 'is_active']),
            models.Index(fields=['role']),
        ]
        # Evitar duplicados de persona-equipo-rol activos dentro de una temporada
        constraints = [
            models.UniqueConstraint(
                fields=['person', 'identity', 'role', 'season'],
                name='unique_active_staff_role',
                condition=models.Q(is_active=True)
            )
        ]

    def __str__(self):
        return f"{self.person.full_name} - {self.get_role_display()} ({self.identity})"
    
    @property
    def display_role(self):
        """Devuelve el rol en formato legible"""
        return self.get_role_display()


class PersonOrganization(models.Model):
    """Pertenencia deportiva de una ficha a un club (#478).

    Estado por club: "está en la plantilla/alta del club". La baja
    (``is_active=False`` con ``end_date``) no toca la ficha global ni los
    roles históricos (siguen visibles en plantillas de temporadas
    anteriores); la relación de seguidor del usuario vive aparte en
    ``users.models.Membership``.
    """
    person = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name='club_memberships',
        verbose_name=_('Persona'),
    )
    organization = models.ForeignKey(
        'core.Organization',
        on_delete=models.CASCADE,
        related_name='person_memberships',
        verbose_name=_('Organización'),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('Activa'),
        help_text=_('¿Está la ficha dada de alta en el club?'),
    )
    start_date = models.DateField(
        auto_now_add=True,
        verbose_name=_('Fecha de alta'),
    )
    end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('Fecha de baja'),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Creado'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('Actualizado'))

    class Meta:
        ordering = ['person__last_name', 'person__first_name']
        verbose_name = _('Pertenencia a club')
        verbose_name_plural = _('Pertenencias a club')
        constraints = [
            models.UniqueConstraint(
                fields=['person', 'organization'],
                name='unique_person_organization',
            )
        ]
        indexes = [
            models.Index(fields=['organization', 'is_active']),
        ]

    def __str__(self):
        return f"{self.person.full_name} - {self.organization.name}"
