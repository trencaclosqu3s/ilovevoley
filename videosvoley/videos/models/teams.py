from django.db import models

from .category import Category


class Club(models.Model):
    federation_id = models.CharField(max_length=200, unique=True)
    official_name = models.CharField(max_length=200)
    president = models.CharField(max_length=200, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    venue_name = models.CharField(max_length=200, blank=True)
    venue_address = models.CharField(max_length=200, blank=True)
    province = models.CharField(max_length=100, blank=True)
    instagram = models.URLField(blank=True)
    facebook = models.URLField(blank=True)
    twitter = models.URLField(blank=True)
    website = models.URLField(blank=True)
    logo_url = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'videos_club'
        ordering = ['official_name']
        verbose_name = 'Club'
        verbose_name_plural = 'Clubes'

    def __str__(self):
        return self.official_name

    @property
    def logo_federation_url(self):
        """Genera URL del logo basada en federation_id"""
        if self.federation_id:
            return f'https://voleibolib.federatio.com/fichas/clubes/{self.federation_id}.jpg'
        return None


class Team(models.Model):
    name = models.CharField(max_length=200)
    federation_id = models.CharField(max_length=200, unique=True)
    club = models.ForeignKey(Club, on_delete=models.SET_NULL, null=True, blank=True, related_name='teams')
    sponsor_name = models.CharField(max_length=200, blank=True, help_text='Nombre con patrocinador si aplica')
    logo_url = models.URLField(blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='teams', help_text='Categoría asignada automáticamente durante el scraping')
    is_active = models.BooleanField(default=True, help_text='Indica si el equipo sigue activo en las competiciones')
    created_at = models.DateTimeField(auto_now_add=True)

    # Sistema de variantes de equipo
    parent_team = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='variants',
        help_text='Equipo principal si este es una variante (ej: Sant Josep A, Sant Josep Groc)'
    )
    variant_type = models.CharField(
        max_length=20,
        choices=[
            ('split', 'División de Equipo (A/B)'),
            ('color', 'Variante de Color (Groc/Lila)'),
            ('temporary', 'Temporal (Torneo)'),
            ('other', 'Otro'),
        ],
        blank=True,
        help_text='Tipo de variante'
    )
    variant_name = models.CharField(
        max_length=50,
        blank=True,
        help_text='Nombre de la variante (ej: "A", "B", "Groc", "Lila")'
    )
    variant_description = models.TextField(
        blank=True,
        help_text='Descripción de la variante'
    )
    is_temporary_variant = models.BooleanField(
        default=False,
        help_text='Marca si es una variante temporal (ej: para un torneo específico)'
    )
    temporary_end_date = models.DateField(
        null=True,
        blank=True,
        help_text='Fecha estimada de finalización si es variante temporal'
    )

    class Meta:
        db_table = 'videos_team'
        ordering = ['name']
        verbose_name = 'Equipo'
        verbose_name_plural = 'Equipos'

    def __str__(self):
        return self.display_name_with_variant

    @property
    def display_logo(self):
        """Devuelve logo del equipo o del club si no tiene"""
        return self.logo_url or (self.club.logo_federation_url if self.club else None)

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
