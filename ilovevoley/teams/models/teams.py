from django.db import models
from django.utils.translation import gettext_lazy as _

from ilovevoley.core.models import GENDER_CHOICES
from ilovevoley.core.tenancy import TeamTenantQuerySet


class Club(models.Model):
    federation_id = models.CharField(max_length=200, unique=True)
    official_name = models.CharField(max_length=200)
    president = models.CharField(max_length=200, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    venue_name = models.CharField(max_length=200, blank=True)
    venue_address = models.CharField(max_length=200, blank=True)
    default_venue = models.ForeignKey(
        'competitions.Venue',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='clubs',
        verbose_name=_('Pabellón habitual')
    )
    municipality = models.CharField(max_length=100, blank=True)
    province = models.CharField(max_length=100, blank=True)
    instagram = models.URLField(blank=True)
    facebook = models.URLField(blank=True)
    twitter = models.URLField(blank=True)
    website = models.URLField(blank=True)
    logo_url = models.URLField(blank=True, null=True)
    logo = models.ImageField(upload_to='clubs/logos/', blank=True, verbose_name=_('Escudo (copia local)'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'videos_club'
        ordering = ['official_name']
        verbose_name = _('Club')
        verbose_name_plural = _('Clubes')

    def __str__(self):
        return self.official_name

    @property
    def logo_federation_url(self):
        """Genera URL del logo basada en federation_id"""
        if self.federation_id:
            return f'https://voleibolib.federatio.com/fichas/clubes/{self.federation_id}.jpg'
        return None


class TeamIdentity(models.Model):
    """Identidad estable de un equipo entre temporadas (#428).

    No confundir con ``federation_id`` (aparición federativa) ni con
    ``parent_team`` / variantes (A/B, color).
    """
    club = models.ForeignKey(
        Club,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='team_identities',
    )
    category = models.ForeignKey(
        'core.Category',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='team_identities',
    )
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True, default='')
    core_name = models.CharField(max_length=200)
    core_name_normalized = models.CharField(max_length=200, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Identidad de equipo')
        verbose_name_plural = _('Identidades de equipo')
        constraints = [
            models.UniqueConstraint(
                fields=['club', 'category', 'gender', 'core_name_normalized'],
                condition=models.Q(club__isnull=False),
                name='unique_team_identity_per_club_category_gender_name',
            ),
        ]

    def __str__(self):
        return self.core_name


class Team(models.Model):
    name = models.CharField(max_length=200)
    federation_id = models.CharField(max_length=200, unique=True)
    club = models.ForeignKey(Club, on_delete=models.SET_NULL, null=True, blank=True, related_name='teams')
    sponsor_name = models.CharField(max_length=200, blank=True, help_text=_('Nombre con patrocinador si aplica'))
    logo_url = models.URLField(blank=True, null=True)
    logo = models.ImageField(upload_to='teams/logos/', blank=True, verbose_name=_('Escudo (copia local)'))
    category = models.ForeignKey(
        'core.Category',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='teams',
        help_text=_('Categoría asignada automáticamente durante el scraping')
    )
    gender = models.CharField(
        max_length=10,
        choices=GENDER_CHOICES,
        blank=True,
        default='',
        verbose_name=_('Género / Rama'),
        help_text=_('Vacío = hereda el género de la categoría.'),
    )
    identity = models.ForeignKey(
        'teams.TeamIdentity',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='teams',
        help_text=_(
            'Identidad estable entre temporadas '
            '(no confundir con federation_id ni con variantes)'
        ),
    )
    is_active = models.BooleanField(default=True, help_text=_('Indica si el equipo sigue activo en las competiciones'))
    created_at = models.DateTimeField(auto_now_add=True)

    # Sistema de variantes de equipo
    parent_team = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='variants',
        help_text=_('Equipo principal si este es una variante (ej: Sant Josep A, Sant Josep Groc)')
    )
    variant_type = models.CharField(
        max_length=20,
        choices=[
            ('split', _('División de Equipo (A/B)')),
            ('color', _('Variante de Color (Groc/Lila)')),
            ('temporary', _('Temporal (Torneo)')),
            ('other', _('Otro')),
        ],
        blank=True,
        help_text=_('Tipo de variante')
    )
    variant_name = models.CharField(
        max_length=50,
        blank=True,
        help_text=_('Nombre de la variante (ej: "A", "B", "Groc", "Lila")')
    )
    variant_description = models.TextField(
        blank=True,
        help_text=_('Descripción de la variante')
    )
    is_temporary_variant = models.BooleanField(
        default=False,
        help_text=_('Marca si es una variante temporal (ej: para un torneo específico)')
    )
    temporary_end_date = models.DateField(
        null=True,
        blank=True,
        help_text=_('Fecha estimada de finalización si es variante temporal')
    )

    objects = TeamTenantQuerySet.as_manager()

    class Meta:
        db_table = 'videos_team'
        ordering = ['name']
        verbose_name = _('Equipo')
        verbose_name_plural = _('Equipos')

    def __str__(self):
        return self.display_name_with_variant

    @property
    def display_logo_file(self):
        """Copia local del escudo, o None.

        Un equipo con ``logo_url`` propio no hereda el escudo del club: hasta que
        se copie el suyo, ``display_logo`` y la story usan esa URL.
        """
        if self.logo:
            return self.logo
        if self.logo_url:
            return None
        if self.club and self.club.logo:
            return self.club.logo
        return None

    @property
    def display_logo(self):
        """URL del escudo: copia local si existe; si no, la de la federación."""
        if self.logo:
            return self.logo.url
        if self.logo_url:
            return self.logo_url
        if self.club:
            return self.club.logo.url if self.club.logo else self.club.logo_federation_url
        return None

    @property
    def effective_gender(self):
        """Género efectivo: el propio si está definido, si no el de la categoría."""
        if self.gender:
            return self.gender
        if self.category_id and self.category:
            return self.category.gender
        return ''

    @property
    def is_variant(self):
        """Returns True if this team is a variant of another"""
        return self.parent_team is not None

    @property
    def root_team(self):
        """Returns the root team (main team)"""
        if self.parent_team:
            return self.parent_team.root_team
        return self

    @property
    def display_name_with_variant(self):
        """Returns full display name including variant"""
        if self.variant_name:
            return f"{self.name} ({self.variant_name})"
        return self.name

    def get_all_variants(self, include_self=True):
        """Returns all variants of this team"""
        if self.parent_team:
            return self.parent_team.get_all_variants(include_self=True)
        else:
            variants = list(self.variants.filter(is_active=True).order_by('variant_name'))
            if include_self:
                variants.insert(0, self)
            return variants


class TeamIdentityCandidate(models.Model):
    """Vínculo de identidad dudoso pendiente de confirmación manual (#428)."""

    STATUS_CHOICES = [
        ('pending', _('Pendiente')),
        ('approved', _('Aprobada')),
        ('rejected', _('Rechazada')),
    ]

    new_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='identity_candidates')
    suggested_identity = models.ForeignKey(
        TeamIdentity,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    suggested_team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    score = models.FloatField(null=True, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Candidata de identidad de equipo')
        verbose_name_plural = _('Candidatas de identidad de equipo')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.new_team} → {self.suggested_identity} ({self.status})'

    def approve(self):
        if self.status != 'pending' or not self.suggested_identity_id:
            return self.new_team
        from django.db import transaction

        with transaction.atomic():
            team = self.new_team
            old_identity_id = team.identity_id
            suggested = self.suggested_identity
            if old_identity_id and old_identity_id != suggested.pk:
                # Candidata de backfill: mover todas las apariciones de la identidad origen
                Team.objects.filter(identity_id=old_identity_id).update(identity=suggested)
            else:
                team.identity = suggested
                team.save(update_fields=['identity'])
            self.status = 'approved'
            self.save(update_fields=['status'])
        return team

    def reject(self):
        if self.status != 'pending':
            return self.new_team
        from django.db import transaction

        from ilovevoley.teams.identity import create_identity_for_team

        with transaction.atomic():
            team = self.new_team
            if team.identity_id:
                # Ya tiene identidad (p. ej. candidata del backfill): solo descartar el vínculo
                self.status = 'rejected'
                self.save(update_fields=['status'])
                return team
            team.identity = create_identity_for_team(team)
            team.save(update_fields=['identity'])
            self.status = 'rejected'
            self.save(update_fields=['status'])
        return team
