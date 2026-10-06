import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ilovevoley.core.tenancy import MatchTenantQuerySet, TenantQuerySet



class LeagueQuerySet(TenantQuerySet):
    """QuerySet de League con los filtros de visibilidad y de tenant."""

    def visible_in_app(self):
        """Ligas que deben mostrarse en la aplicación principal"""
        return self.filter(
            is_active=True,
            visibility_type='main',
            is_our_team_related=True
        )

    def for_tenant(self, tenant, *, visible_only=True):
        """Ligas (por defecto visibles) donde participa un equipo del club del tenant.

        Con la FK ``Organization.club`` se restringe la lista global a las
        ligas que realmente interesan al tenant. Para tenants sin club
        vinculado (selecciones) se mantiene el comportamiento global.
        """
        from django.db.models import Q
        from ilovevoley.core.mixins import (
            get_club_team_filter,
            get_tenant_club,
        )
        from ilovevoley.teams.models import Team

        if tenant is None:
            return self.none()
        qs = self.visible_in_app() if visible_only else self
        if get_tenant_club(tenant) is None:
            return qs
        matches_q = get_club_team_filter(tenant)
        league_q = Q(matches__in=Match.objects.filter(matches_q)) | Q(standings__team__in=Team.objects.for_tenant(tenant))
        return qs.filter(league_q).distinct()



    def reference_leagues(self):
        """Ligas de referencia (solo admin)"""
        return self.filter(
            visibility_type__in=['reference', 'historical', 'external']
        )

    def historical_leagues(self):
        """Ligas históricas"""
        return self.filter(
            visibility_type='historical',
            is_historical=True
        )

    def external_leagues(self):
        """Ligas externas (no relacionadas con nuestro equipo)"""
        return self.filter(
            visibility_type='external',
            is_our_team_related=False
        )

    def all_for_admin(self):
        """Todas las ligas para el admin"""
        return self.all()


# Nombre público histórico del manager (reexportado por ``videos.models``).
LeagueManager = models.Manager.from_queryset(LeagueQuerySet)


class League(models.Model):
    COMPETITION_TYPES = [
        ('regular', _('Liga Regular')),
        ('playoff', _('Playoff')),
        ('cup', _('Copa')),
        ('friendly', _('Amistoso')),
    ]

    VISIBILITY_TYPES = [
        ('main', _('Principal (mostrar en app)')),
        ('reference', _('Referencia (solo admin)')),
        ('historical', _('Histórica (solo admin)')),
        ('external', _('Externa (solo admin)')),
    ]

    MATCH_FORMAT_CHOICES = [
        ('standard', _('Estándar (5 sets, ganar 3)')),
        ('alevin_balear', _('Alevín Balear (3 sets, jugar los 3)')),
        ('tournament_3sets', _('Torneo 3 sets (ganar 2)')),
        ('custom', _('Personalizado')),
    ]

    name = models.CharField(max_length=200)
    federation_id = models.CharField(max_length=200, unique=True)
    competition_type = models.CharField(max_length=20, choices=COMPETITION_TYPES, default='regular')
    season = models.ForeignKey(
        'core.Season',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='leagues',
        verbose_name=_('Temporada'),
    )
    # Nuevo campo para soporte multi-categoría (torneos, copas)
    categories = models.ManyToManyField(
        'core.Category',
        blank=True,
        related_name='leagues',
        db_table='videos_league_categories',
        help_text=_('Categorías de la liga (puede ser múltiple para torneos/copas)')
    )
    is_active = models.BooleanField(default=True)
    visibility_type = models.CharField(
        max_length=20,
        choices=VISIBILITY_TYPES,
        default='main',
        help_text=_('Controla dónde se muestra la liga: Principal (en la app), Referencia (solo admin), Histórica (datos antiguos), Externa (otras ligas)')
    )
    is_historical = models.BooleanField(
        default=False,
        help_text=_('Indica si es una liga de temporadas anteriores')
    )
    is_our_team_related = models.BooleanField(
        default=True,
        help_text=_('Indica si esta liga está relacionada con nuestro equipo')
    )
    match_format = models.CharField(
        max_length=20,
        choices=MATCH_FORMAT_CHOICES,
        default='standard',
        help_text=_('Formato de partido para esta liga')
    )
    custom_max_sets = models.IntegerField(
        null=True,
        blank=True,
        help_text=_('Máximo de sets (solo si formato es personalizado)')
    )
    custom_sets_to_win = models.IntegerField(
        null=True,
        blank=True,
        help_text=_('Sets necesarios para ganar (solo si formato es personalizado)')
    )
    created_at = models.DateTimeField(auto_now_add=True)
    base_url = models.URLField(default='https://www.voleibolib.net')

    # Sistema de fases de liga
    parent_league = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='phases',
        help_text=_('Liga padre si esta es una fase (ej: Liguilla Oro es fase de Liga Regular)')
    )
    phase_name = models.CharField(
        max_length=100,
        blank=True,
        help_text=_('Nombre de la fase (ej: "Liguilla Oro", "Liguilla Plata", "Playoffs")')
    )
    phase_order = models.IntegerField(
        default=0,
        help_text=_('Orden de la fase (0 = liga principal, 1+ = fases subsecuentes)')
    )
    display_name_override = models.CharField(
        max_length=200,
        blank=True,
        help_text=_('Nombre personalizado para mostrar (opcional)')
    )

    objects = LeagueManager()

    class Meta:
        db_table = 'videos_league'
        ordering = ['-created_at']
        verbose_name = _('Liga')
        verbose_name_plural = _('Ligas')

    def __str__(self):
        season = self.season.name if self.season_id else '—'
        return f'{self.name} ({season})'

    @property
    def has_pending_matches(self):
        """Indica si la liga tiene partidos pendientes (programados o en curso)"""
        if hasattr(self, 'has_pending_matches_annotated'):
            return bool(self.has_pending_matches_annotated)
        from django.utils import timezone
        now = timezone.now()
        return self.matches.filter(
            status__in=['scheduled', 'in_progress'],
            match_date__gte=now
        ).exists()

    @property
    def should_show_in_app(self):
        """Indica si la liga debe mostrarse en la aplicación principal"""
        return (
            self.is_active and
            self.visibility_type == 'main' and
            self.is_our_team_related
        )

    @property
    def is_reference_league(self):
        """Indica si es una liga de referencia (solo para admin)"""
        return self.visibility_type in ['reference', 'historical', 'external']

    @property
    def is_past_league(self):
        """Indica si la liga es del pasado (sin partidos pendientes)"""
        return not self.has_pending_matches

    @property
    def has_standings(self):
        """Indica si la liga tiene registros de clasificación"""
        if hasattr(self, 'standings_count'):
            return self.standings_count > 0
        return self.standings.exists()

    @property
    def is_phase(self):
        """Returns True if this league is a phase of another league"""
        return self.parent_league is not None

    @property
    def root_league(self):
        """Returns the root league (traverses up parent chain)"""
        if self.parent_league:
            return self.parent_league.root_league
        return self

    @property
    def display_name(self):
        """Returns the display name with phase info"""
        if self.display_name_override:
            return self.display_name_override
        if self.phase_name:
            return f"{self.name} - {self.phase_name}"
        return self.name

    def get_all_phases(self, include_self=True):
        """Returns all phases of this league including itself"""
        if self.parent_league:
            return self.parent_league.get_all_phases(include_self=True)
        else:
            phases = list(self.phases.filter(is_active=True).order_by('phase_order'))
            if include_self:
                phases.insert(0, self)
            return phases

    def get_combined_matches(self):
        """Returns matches from this league and all its phases"""
        if self.parent_league:
            return self.parent_league.get_combined_matches()
        else:
            league_ids = [self.id] + list(self.phases.values_list('id', flat=True))
            return Match.objects.filter(league_id__in=league_ids)


class Venue(models.Model):
    name = models.CharField(
        max_length=200,
        unique=True,
        verbose_name=_('Nombre oficial'),
        help_text=_('Nombre canónico del pabellón o instalación deportiva')
    )
    short_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_('Nombre corto'),
        help_text=_('Nombre abreviado para listados compactos')
    )
    address = models.CharField(
        max_length=500,
        blank=True,
        verbose_name=_('Dirección'),
        help_text=_('Dirección física completa (calle, número)')
    )
    city = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_('Municipio')
    )
    postal_code = models.CharField(
        max_length=10,
        blank=True,
        verbose_name=_('Código postal')
    )
    google_maps_url = models.URLField(
        max_length=500,
        blank=True,
        verbose_name=_('Enlace Google Maps'),
        help_text=_('Enlace corto o directo a la ubicación en Google Maps (ej. https://maps.app.goo.gl/...)')
    )
    aliases = models.TextField(
        blank=True,
        verbose_name=_('Nombres alternativos / Alias'),
        help_text=_('Variaciones de nombre separadas por coma o salto de línea usadas en federación (ej: Pav. Municipal Alaró, Pista 1, Pista 2)')
    )
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name=_('Latitud')
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name=_('Longitud')
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('Activo')
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'videos_venue'
        ordering = ['city', 'name']
        verbose_name = _('Pabellón / Sede')
        verbose_name_plural = _('Pabellones / Sedes')

    def __str__(self):
        if self.city:
            return f'{self.name} ({self.city})'
        return self.name

    @property
    def full_address(self) -> str:
        """Devuelve la dirección física completa limpia para geocodificación RFC 5545."""
        parts = []
        if self.name:
            parts.append(self.name.strip())
        if self.address:
            addr = self.address.strip()
            # Si la dirección contiene partes repetidas del nombre (ej: "Germans Escalas, Mare de Deu..."),
            # limpiamos los fragmentos que ya están en el nombre
            addr_parts = [p.strip() for p in addr.split(',') if p.strip()]
            cleaned_addr_parts = [
                p for p in addr_parts
                if p.lower() not in (self.name or '').lower()
            ]
            if cleaned_addr_parts:
                parts.append(', '.join(cleaned_addr_parts))
            elif addr.lower() not in (self.name or '').lower():
                parts.append(addr)
        if self.city:
            city_str = self.city.strip()
            if not any(city_str.lower() in p.lower() for p in parts):
                parts.append(city_str)
        return ', '.join(parts) if parts else _('Por confirmar')

    @property
    def maps_url(self) -> str | None:
        """Devuelve la URL directa a Maps o una URL de búsqueda como fallback."""
        if self.google_maps_url:
            return self.google_maps_url
        if self.latitude is not None and self.longitude is not None:
            return f'https://www.google.com/maps/search/?api=1&query={self.latitude},{self.longitude}'
        if self.full_address and self.full_address != _('Por confirmar'):
            import urllib.parse
            query = urllib.parse.quote_plus(self.full_address)
            return f'https://www.google.com/maps/search/?api=1&query={query}'
        return None

    def matches_text(self, text: str) -> bool:
        """Verifica si un texto coincide con el nombre o alguno de los alias."""
        if not text:
            return False
        clean_text = text.strip().lower()
        if clean_text == self.name.strip().lower():
            return True
        if self.short_name and clean_text == self.short_name.strip().lower():
            return True
        if self.aliases:
            for alias in self.aliases.replace('\n', ',').split(','):
                alias_clean = alias.strip().lower()
                if alias_clean and (clean_text == alias_clean or alias_clean in clean_text or clean_text in alias_clean):
                    return True
        return False


class MatchManager(models.Manager.from_queryset(MatchTenantQuerySet)):
    """Manager por defecto: excluye withdrawn y acota por club del tenant."""
    def get_queryset(self):
        return super().get_queryset().exclude(status='withdrawn')


class MatchAllManager(models.Manager.from_queryset(MatchTenantQuerySet)):
    """Manager que incluye TODOS los partidos, incluyendo withdrawn"""
    pass


class Match(models.Model):
    MATCH_STATES = [
        ('scheduled', _('Programado')),
        ('in_progress', _('En Progreso')),
        ('finished', _('Finalizado')),
        ('postponed', _('Aplazado')),
        ('cancelled', _('Cancelado')),
        ('withdrawn', _('Retirado (equipo fuera de liga)')),
    ]

    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name='matches', null=True, blank=True)
    home_team = models.ForeignKey('teams.Team', on_delete=models.CASCADE, related_name='home_matches', null=True, blank=True)
    away_team = models.ForeignKey('teams.Team', on_delete=models.CASCADE, related_name='away_matches', null=True, blank=True)

    # Campos para partidos amistosos con equipos no registrados
    home_team_text = models.CharField(
        max_length=200,
        blank=True,
        help_text=_('Nombre del equipo local para partidos amistosos sin equipo en BD')
    )
    away_team_text = models.CharField(
        max_length=200,
        blank=True,
        help_text=_('Nombre del equipo visitante para partidos amistosos sin equipo en BD')
    )
    is_friendly = models.BooleanField(
        default=False,
        help_text=_('Indica si es un partido amistoso creado manualmente')
    )
    match_date = models.DateTimeField()
    venue = models.CharField(max_length=200, blank=True)
    venue_ref = models.ForeignKey(
        Venue,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='matches',
        verbose_name=_('Pabellón')
    )
    city = models.CharField(max_length=100, blank=True)
    round_number = models.IntegerField(default=1)
    home_score = models.IntegerField(null=True, blank=True)
    away_score = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=MATCH_STATES, default='scheduled')
    federation_id = models.CharField(max_length=200, unique=True, null=True, blank=True)

    # Información de árbitros y personal técnico
    referee1 = models.CharField(max_length=200, blank=True, verbose_name=_('Árbitro 1'))
    referee2 = models.CharField(max_length=200, blank=True, verbose_name=_('Árbitro 2'))
    scorer = models.CharField(max_length=200, blank=True, verbose_name=_('Anotador'))
    timekeeper = models.CharField(max_length=200, blank=True, verbose_name=_('Cronometrador'))
    delegate = models.CharField(max_length=200, blank=True, verbose_name=_('Delegado'))

    # Información detallada del campo
    field_address = models.CharField(max_length=500, blank=True, verbose_name=_('Dirección del Campo'))

    # IDs de la federación para matching
    federation_club_local_id = models.CharField(max_length=50, blank=True, verbose_name=_('ID Club Local (Federación)'))
    federation_club_away_id = models.CharField(max_length=50, blank=True, verbose_name=_('ID Club Visitante (Federación)'))

    # Información de acta oficial
    acta_html = models.CharField(max_length=200, blank=True, verbose_name=_('Acta HTML'))
    acta_data = models.JSONField(
        null=True, blank=True, verbose_name=_('Acta parseada'),
        help_text=_('JSON estructurado del acta federativa (convocados, alineaciones y sets)'),
    )
    set_scores = models.JSONField(
        null=True, blank=True, verbose_name=_('Parciales'),
        help_text=_(
            'Parciales del partido [[local, visitante], ...]. Procede del scraping '
            'de resultados o de la entrada manual; el acta tiene prioridad.'
        ),
    )
    result_penalized = models.BooleanField(
        default=False, verbose_name=_('Resuelto por penalización'),
        help_text=_(
            'El resultado oficial (home_score/away_score) no refleja el juego del '
            'acta por una penalización o incomparecencia.'
        ),
    )

    result_notified_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_('Resultado notificado el'),
        help_text=_('Fecha y hora en que se envió la notificación push del resultado para evitar duplicados.'),
    )
    reminder_sent_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_('Recordatorio 2h enviado el'),
        help_text=_('Fecha y hora en que se envió el recordatorio push 2h antes del partido para evitar duplicados.'),
    )
    photo_reminder_sent_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_('Recordatorio de fotos enviado el'),
        help_text=_('Fecha y hora en que se envió el push para animar a subir fotos del partido, para evitar duplicados.'),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    # Managers
    objects = MatchManager()  # Manager por defecto: excluye withdrawn
    all_objects = MatchAllManager()  # Manager completo: incluye withdrawn

    class Meta:
        db_table = 'videos_match'
        ordering = ['match_date']
        verbose_name = _('Partido')
        verbose_name_plural = _('Partidos')
        indexes = [
            models.Index(fields=['match_date'], name='match_date_idx'),
            models.Index(fields=['league', 'match_date'], name='match_league_date_idx'),
        ]

    def __str__(self):
        base = f'{self.home_team_display} vs {self.away_team_display} - {self.match_date.strftime("%d/%m/%Y")}'
        if self.league_id:
            cats = self.league.categories.all()
            if cats:
                return f'{base} [{", ".join(c.name for c in cats)}]'
        return base

    @property
    def is_finished(self):
        return self.status == 'finished'

    @property
    def result_display(self):
        if self.home_score is not None and self.away_score is not None:
            return f'{self.home_score} - {self.away_score}'
        return _('Sin resultado')

    @property
    def home_team_display(self):
        """Retorna el nombre del equipo local (Team o texto)"""
        if self.home_team:
            return self.home_team.name
        return self.home_team_text or _('Equipo Local')

    @property
    def away_team_display(self):
        """Retorna el nombre del equipo visitante (Team o texto)"""
        if self.away_team:
            return self.away_team.name
        return self.away_team_text or _('Equipo Visitante')

    @property
    def is_official(self):
        """Indica si es un partido oficial (scrapeado)"""
        return not self.is_friendly and self.federation_id is not None

    def clean(self):
        """Validar consistencia de los campos del partido"""
        from django.core.exceptions import ValidationError

        # Solo validar equipos para partidos NO amistosos que no estén en proceso de creación
        # Para amistosos, el formulario ya se encarga de la validación
        if not self.is_friendly and self.pk is not None:
            # Validar equipo local para partidos oficiales ya guardados
            if not self.home_team and not self.home_team_text:
                raise ValidationError(_('Debe especificar un equipo local (seleccionado o texto)'))

            # Validar equipo visitante para partidos oficiales ya guardados
            if not self.away_team and not self.away_team_text:
                raise ValidationError(_('Debe especificar un equipo visitante (seleccionado o texto)'))

        # Si es amistoso, validar que no tenga federation_id
        if self.is_friendly and self.federation_id:
            raise ValidationError(_('Los partidos amistosos no deben tener federation_id'))

        # Si tiene federation_id, no debe ser amistoso
        if self.federation_id and self.is_friendly:
            self.is_friendly = False  # Auto-corregir

    @property
    def official_acta_url(self) -> str:
        """URL canónica del acta oficial en el servidor federativo."""
        if not self.acta_html:
            return ''
        if self.acta_html.startswith(('http://', 'https://')):
            return self.acta_html
        if self.federation_id:
            return f"https://voleibolib.federatio.com/actas/{self.federation_id}/{self.acta_html}"
        return self.acta_html

    def save(self, *args, **kwargs):
        if self.acta_html and not self.acta_html.startswith(('http://', 'https://')) and self.federation_id:
            self.acta_html = f"https://voleibolib.federatio.com/actas/{self.federation_id}/{self.acta_html}"
            update_fields = kwargs.get('update_fields')
            if update_fields is not None and 'acta_html' not in update_fields:
                kwargs['update_fields'] = list(update_fields) + ['acta_html']
        super().save(*args, **kwargs)


class ScrapingEndpoint(models.Model):
    ENDPOINT_TYPES = [
        ('standings', _('Clasificación')),
        ('results', _('Resultados')),
        ('calendar', _('Calendario')),
        ('json_results', _('Resultados JSON')),
    ]

    PARSER_TYPES = [
        ('table_standings', _('Tabla de Clasificación')),
        ('match_results', _('Resultados de Partidos')),
        ('match_calendar', _('Calendario de Partidos')),
        ('json_matches', _('Partidos JSON (próximos)')),
        ('json_results', _('Resultados JSON (finalizados)')),
        ('json_unified', _('JSON Unificado (configurable)')),
    ]

    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name='endpoints')
    endpoint_type = models.CharField(max_length=20, choices=ENDPOINT_TYPES)
    url_pattern = models.CharField(max_length=500, help_text=_('Usar {league_id}, {round}, etc. para parámetros dinámicos'))
    parser_type = models.CharField(max_length=30, choices=PARSER_TYPES)
    is_active = models.BooleanField(default=True)
    extra_params = models.JSONField(default=dict, blank=True, help_text=_('Parámetros adicionales como JSON'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'videos_scrapingendpoint'
        verbose_name = _('Endpoint de Scraping')
        verbose_name_plural = _('Endpoints de Scraping')
        unique_together = ['league', 'endpoint_type']

    def __str__(self):
        return f'{self.league.name} - {self.get_endpoint_type_display()}'

    def get_full_url(self, **kwargs):
        """Construye la URL completa reemplazando parámetros"""
        url = self.url_pattern.format(league_id=self.league.federation_id, **kwargs)
        if not url.startswith('http'):
            url = f'{self.league.base_url}/{url.lstrip("/")}'
        return url


class StandingQuerySet(TenantQuerySet):
    """QuerySet de Standing con ámbito de tenant a través de sus ligas."""

    def for_tenant(self, tenant, *, visible_only=True):
        if tenant is None:
            return self.none()
        return self.filter(league__in=League.objects.for_tenant(tenant, visible_only=visible_only))


StandingManager = models.Manager.from_queryset(StandingQuerySet)


class Standing(models.Model):
    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name='standings')
    team = models.ForeignKey('teams.Team', on_delete=models.CASCADE, related_name='standings')
    objects = StandingManager()

    position = models.IntegerField()
    played = models.IntegerField(default=0)
    won = models.IntegerField(default=0)
    lost = models.IntegerField(default=0)
    sets_for = models.IntegerField(default=0)
    sets_against = models.IntegerField(default=0)
    points_for = models.IntegerField(default=0)
    points_against = models.IntegerField(default=0)
    total_points = models.IntegerField(default=0)
    wins_3_0 = models.IntegerField(default=0, verbose_name=_('Victorias 3-0'))
    wins_3_1 = models.IntegerField(default=0, verbose_name=_('Victorias 3-1'))
    wins_3_2 = models.IntegerField(default=0, verbose_name=_('Victorias 3-2'))
    losses_2_3 = models.IntegerField(default=0, verbose_name=_('Derrotas 2-3'))
    losses_1_3 = models.IntegerField(default=0, verbose_name=_('Derrotas 1-3'))
    losses_0_3 = models.IntegerField(default=0, verbose_name=_('Derrotas 0-3'))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'videos_standing'
        ordering = ['position']
        verbose_name = _('Clasificación')
        verbose_name_plural = _('Clasificaciones')
        unique_together = ['league', 'team']

    def __str__(self):
        return f'{self.position}. {self.team.name} - {self.total_points} pts'

    @property
    def set_difference(self):
        return self.sets_for - self.sets_against

    @property
    def point_difference(self):
        return self.points_for - self.points_against


class MatchShareLink(models.Model):
    """Enlace público temporal y revocable para compartir la ficha de un partido."""

    match = models.ForeignKey(
        Match, on_delete=models.CASCADE, related_name='share_links'
    )
    organization = models.ForeignKey(
        'core.Organization', on_delete=models.CASCADE, related_name='match_share_links'
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='match_share_links'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Enlace de partido')
        verbose_name_plural = _('Enlaces de partido')
        indexes = [
            models.Index(fields=['match', '-created_at'], name='share_match_created_idx'),
        ]

    def __str__(self):
        return f'{self.match} → {self.token}'

    @property
    def is_active(self):
        return self.revoked_at is None and self.expires_at > timezone.now()

    def revoke(self):
        self.revoked_at = timezone.now()
        self.save(update_fields=['revoked_at'])


class MatchLineup(models.Model):
    """Aparición de un deportista en un partido, derivada del acta federativa.

    Se crea una fila por (partido, equipo, dorsal) al persistir el JSON del
    acta. ``person`` queda vacío cuando el dorsal del acta no casa con ningún
    ``PlayerRole`` del equipo en la temporada; estos registros se conservan
    para poder re-resolverlos si más adelante se registra la plantilla.
    """

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='match_lineups')
    team = models.ForeignKey('teams.Team', on_delete=models.CASCADE, related_name='match_lineups')
    person = models.ForeignKey(
        'rosters.Person', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='match_lineups', verbose_name=_('Deportista'),
    )

    jersey_number = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name=_('Dorsal'))
    name_acta = models.CharField(max_length=200, blank=True, verbose_name=_('Nombre en acta'))

    is_convocado = models.BooleanField(default=False, verbose_name=_('Convocado'))
    sets_played = models.PositiveSmallIntegerField(default=0, verbose_name=_('Sets jugados'))
    sets_started = models.PositiveSmallIntegerField(default=0, verbose_name=_('Sets como titular'))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'videos_matchlineup'
        ordering = ['match', 'team', 'jersey_number']
        verbose_name = _('Alineación de partido')
        verbose_name_plural = _('Alineaciones de partido')
        indexes = [
            models.Index(fields=['person', 'match'], name='lineup_person_match_idx'),
            models.Index(fields=['team', 'match'], name='lineup_team_match_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['match', 'team', 'jersey_number'],
                name='unique_lineup_jersey_per_match',
                condition=models.Q(jersey_number__isnull=False),
            ),
        ]

    def __str__(self):
        quien = self.person.full_name if self.person else self.name_acta or _('Sin identificar')
        dorsal = f' #{self.jersey_number}' if self.jersey_number else ''
        return f'{quien}{dorsal} - {self.match_id}'


class MatchChangeLogQuerySet(TenantQuerySet):
    """QuerySet de MatchChangeLog con ámbito de tenant a través de sus partidos."""

    def for_tenant(self, tenant):
        if tenant is None:
            return self.none()
        return self.filter(match__in=Match.all_objects.for_tenant(tenant))



MatchChangeLogManager = models.Manager.from_queryset(MatchChangeLogQuerySet)


class MatchChangeLog(models.Model):
    CHANGE_TYPES = [
        ('datetime', _('Fecha / Hora')),
        ('venue', _('Sede / Pabellón')),
        ('status', _('Estado')),
        ('score', _('Tanteo / Resultado')),
        ('other', _('Otro')),
    ]

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='change_logs')
    change_type = models.CharField(max_length=20, choices=CHANGE_TYPES, default='other')
    field_name = models.CharField(max_length=50)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    is_last_minute = models.BooleanField(
        default=False,
        help_text=_('Indica si el cambio se detectó con menos de 7 días de antelación al partido')
    )
    detected_at = models.DateTimeField(auto_now_add=True)
    notified = models.BooleanField(default=False)
    notified_at = models.DateTimeField(null=True, blank=True)
    reviewed = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_match_changes',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    objects = MatchChangeLogManager()

    class Meta:
        db_table = 'videos_matchchangelog'
        ordering = ['-detected_at']
        verbose_name = _('Modificación de Partido')
        verbose_name_plural = _('Modificaciones de Partidos')
        indexes = [
            models.Index(fields=['match', 'detected_at'], name='match_change_match_idx'),
            models.Index(fields=['is_last_minute', 'notified'], name='match_change_notif_idx'),
            # Panel de revisión: filtros primarios son reviewed + orden -detected_at.
            models.Index(fields=['reviewed', '-detected_at'], name='match_change_review_idx'),
        ]

    def __str__(self):
        return f'{self.match} - {self.get_change_type_display()} ({self.field_name}): {self.old_value} -> {self.new_value}'
