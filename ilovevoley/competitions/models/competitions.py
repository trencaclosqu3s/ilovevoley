from django.db import models

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

    def for_tenant(self, tenant):
        """Ligas visibles donde participa un equipo del club del tenant.

        Con la FK ``Organization.club`` se restringe la lista global a las
        ligas que realmente interesan al tenant. Para tenants sin club
        vinculado (selecciones) se mantiene el comportamiento global.
        """
        from ilovevoley.core.mixins import get_club_team_filter, get_tenant_club

        if tenant is None:
            return self.none()
        qs = self.visible_in_app()
        if get_tenant_club(tenant) is None:
            return qs
        return qs.filter(
            matches__in=Match.objects.filter(get_club_team_filter(tenant))
        ).distinct()

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
        ('regular', 'Liga Regular'),
        ('playoff', 'Playoff'),
        ('cup', 'Copa'),
        ('friendly', 'Amistoso'),
    ]

    VISIBILITY_TYPES = [
        ('main', 'Principal (mostrar en app)'),
        ('reference', 'Referencia (solo admin)'),
        ('historical', 'Histórica (solo admin)'),
        ('external', 'Externa (solo admin)'),
    ]

    MATCH_FORMAT_CHOICES = [
        ('standard', 'Estándar (5 sets, ganar 3)'),
        ('alevin_balear', 'Alevín Balear (3 sets, jugar los 3)'),
        ('tournament_3sets', 'Torneo 3 sets (ganar 2)'),
        ('custom', 'Personalizado'),
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
        verbose_name='Temporada',
    )
    # Nuevo campo para soporte multi-categoría (torneos, copas)
    categories = models.ManyToManyField(
        'core.Category',
        blank=True,
        related_name='leagues',
        db_table='videos_league_categories',
        help_text='Categorías de la liga (puede ser múltiple para torneos/copas)'
    )
    is_active = models.BooleanField(default=True)
    visibility_type = models.CharField(
        max_length=20,
        choices=VISIBILITY_TYPES,
        default='main',
        help_text='Controla dónde se muestra la liga: Principal (en la app), Referencia (solo admin), Histórica (datos antiguos), Externa (otras ligas)'
    )
    is_historical = models.BooleanField(
        default=False,
        help_text='Indica si es una liga de temporadas anteriores'
    )
    is_our_team_related = models.BooleanField(
        default=True,
        help_text='Indica si esta liga está relacionada con nuestro equipo'
    )
    match_format = models.CharField(
        max_length=20,
        choices=MATCH_FORMAT_CHOICES,
        default='standard',
        help_text='Formato de partido para esta liga'
    )
    custom_max_sets = models.IntegerField(
        null=True,
        blank=True,
        help_text='Máximo de sets (solo si formato es personalizado)'
    )
    custom_sets_to_win = models.IntegerField(
        null=True,
        blank=True,
        help_text='Sets necesarios para ganar (solo si formato es personalizado)'
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
        help_text='Liga padre si esta es una fase (ej: Liguilla Oro es fase de Liga Regular)'
    )
    phase_name = models.CharField(
        max_length=100,
        blank=True,
        help_text='Nombre de la fase (ej: "Liguilla Oro", "Liguilla Plata", "Playoffs")'
    )
    phase_order = models.IntegerField(
        default=0,
        help_text='Orden de la fase (0 = liga principal, 1+ = fases subsecuentes)'
    )
    display_name_override = models.CharField(
        max_length=200,
        blank=True,
        help_text='Nombre personalizado para mostrar (opcional)'
    )

    objects = LeagueManager()

    class Meta:
        db_table = 'videos_league'
        ordering = ['-created_at']
        verbose_name = 'Liga'
        verbose_name_plural = 'Ligas'

    def __str__(self):
        season = self.season.name if self.season_id else '—'
        return f'{self.name} ({season})'

    @property
    def has_pending_matches(self):
        """Indica si la liga tiene partidos pendientes (programados o en curso)"""
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


class MatchManager(models.Manager.from_queryset(MatchTenantQuerySet)):
    """Manager por defecto: excluye withdrawn y acota por club del tenant."""
    def get_queryset(self):
        return super().get_queryset().exclude(status='withdrawn')


class MatchAllManager(models.Manager.from_queryset(MatchTenantQuerySet)):
    """Manager que incluye TODOS los partidos, incluyendo withdrawn"""
    pass


class Match(models.Model):
    MATCH_STATES = [
        ('scheduled', 'Programado'),
        ('in_progress', 'En Progreso'),
        ('finished', 'Finalizado'),
        ('postponed', 'Aplazado'),
        ('cancelled', 'Cancelado'),
        ('withdrawn', 'Retirado (equipo fuera de liga)'),
    ]

    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name='matches', null=True, blank=True)
    home_team = models.ForeignKey('teams.Team', on_delete=models.CASCADE, related_name='home_matches', null=True, blank=True)
    away_team = models.ForeignKey('teams.Team', on_delete=models.CASCADE, related_name='away_matches', null=True, blank=True)

    # Campos para partidos amistosos con equipos no registrados
    home_team_text = models.CharField(
        max_length=200,
        blank=True,
        help_text='Nombre del equipo local para partidos amistosos sin equipo en BD'
    )
    away_team_text = models.CharField(
        max_length=200,
        blank=True,
        help_text='Nombre del equipo visitante para partidos amistosos sin equipo en BD'
    )
    is_friendly = models.BooleanField(
        default=False,
        help_text='Indica si es un partido amistoso creado manualmente'
    )
    match_date = models.DateTimeField()
    venue = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    round_number = models.IntegerField(default=1)
    home_score = models.IntegerField(null=True, blank=True)
    away_score = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=MATCH_STATES, default='scheduled')
    federation_id = models.CharField(max_length=200, unique=True, null=True, blank=True)

    # Información de árbitros y personal técnico
    referee1 = models.CharField(max_length=200, blank=True, verbose_name='Árbitro 1')
    referee2 = models.CharField(max_length=200, blank=True, verbose_name='Árbitro 2')
    scorer = models.CharField(max_length=200, blank=True, verbose_name='Anotador')
    timekeeper = models.CharField(max_length=200, blank=True, verbose_name='Cronometrador')
    delegate = models.CharField(max_length=200, blank=True, verbose_name='Delegado')

    # Información detallada del campo
    field_address = models.CharField(max_length=500, blank=True, verbose_name='Dirección del Campo')

    # IDs de la federación para matching
    federation_club_local_id = models.CharField(max_length=50, blank=True, verbose_name='ID Club Local (Federación)')
    federation_club_away_id = models.CharField(max_length=50, blank=True, verbose_name='ID Club Visitante (Federación)')

    # Información de acta oficial
    acta_html = models.CharField(max_length=200, blank=True, verbose_name='Acta HTML')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Managers
    objects = MatchManager()  # Manager por defecto: excluye withdrawn
    all_objects = MatchAllManager()  # Manager completo: incluye withdrawn

    class Meta:
        db_table = 'videos_match'
        ordering = ['match_date']
        verbose_name = 'Partido'
        verbose_name_plural = 'Partidos'

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
        return 'Sin resultado'

    @property
    def home_team_display(self):
        """Retorna el nombre del equipo local (Team o texto)"""
        if self.home_team:
            return self.home_team.name
        return self.home_team_text or 'Equipo Local'

    @property
    def away_team_display(self):
        """Retorna el nombre del equipo visitante (Team o texto)"""
        if self.away_team:
            return self.away_team.name
        return self.away_team_text or 'Equipo Visitante'

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
                raise ValidationError('Debe especificar un equipo local (seleccionado o texto)')

            # Validar equipo visitante para partidos oficiales ya guardados
            if not self.away_team and not self.away_team_text:
                raise ValidationError('Debe especificar un equipo visitante (seleccionado o texto)')

        # Si es amistoso, validar que no tenga federation_id
        if self.is_friendly and self.federation_id:
            raise ValidationError('Los partidos amistosos no deben tener federation_id')

        # Si tiene federation_id, no debe ser amistoso
        if self.federation_id and self.is_friendly:
            self.is_friendly = False  # Auto-corregir


class ScrapingEndpoint(models.Model):
    ENDPOINT_TYPES = [
        ('standings', 'Clasificación'),
        ('results', 'Resultados'),
        ('calendar', 'Calendario'),
        ('json_results', 'Resultados JSON'),
    ]

    PARSER_TYPES = [
        ('table_standings', 'Tabla de Clasificación'),
        ('match_results', 'Resultados de Partidos'),
        ('match_calendar', 'Calendario de Partidos'),
        ('json_matches', 'Partidos JSON (próximos)'),
        ('json_results', 'Resultados JSON (finalizados)'),
        ('json_unified', 'JSON Unificado (configurable)'),
    ]

    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name='endpoints')
    endpoint_type = models.CharField(max_length=20, choices=ENDPOINT_TYPES)
    url_pattern = models.CharField(max_length=500, help_text='Usar {league_id}, {round}, etc. para parámetros dinámicos')
    parser_type = models.CharField(max_length=30, choices=PARSER_TYPES)
    is_active = models.BooleanField(default=True)
    extra_params = models.JSONField(default=dict, blank=True, help_text='Parámetros adicionales como JSON')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'videos_scrapingendpoint'
        verbose_name = 'Endpoint de Scraping'
        verbose_name_plural = 'Endpoints de Scraping'
        unique_together = ['league', 'endpoint_type']

    def __str__(self):
        return f'{self.league.name} - {self.get_endpoint_type_display()}'

    def get_full_url(self, **kwargs):
        """Construye la URL completa reemplazando parámetros"""
        url = self.url_pattern.format(league_id=self.league.federation_id, **kwargs)
        if not url.startswith('http'):
            url = f'{self.league.base_url}/{url.lstrip("/")}'
        return url


class Standing(models.Model):
    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name='standings')
    team = models.ForeignKey('teams.Team', on_delete=models.CASCADE, related_name='standings')
    position = models.IntegerField()
    played = models.IntegerField(default=0)
    won = models.IntegerField(default=0)
    lost = models.IntegerField(default=0)
    sets_for = models.IntegerField(default=0)
    sets_against = models.IntegerField(default=0)
    points_for = models.IntegerField(default=0)
    points_against = models.IntegerField(default=0)
    total_points = models.IntegerField(default=0)
    wins_3_0 = models.IntegerField(default=0, verbose_name='Victorias 3-0')
    wins_3_1 = models.IntegerField(default=0, verbose_name='Victorias 3-1')
    wins_3_2 = models.IntegerField(default=0, verbose_name='Victorias 3-2')
    losses_2_3 = models.IntegerField(default=0, verbose_name='Derrotas 2-3')
    losses_1_3 = models.IntegerField(default=0, verbose_name='Derrotas 1-3')
    losses_0_3 = models.IntegerField(default=0, verbose_name='Derrotas 0-3')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'videos_standing'
        ordering = ['position']
        verbose_name = 'Clasificación'
        verbose_name_plural = 'Clasificaciones'
        unique_together = ['league', 'team']

    def __str__(self):
        return f'{self.position}. {self.team.name} - {self.total_points} pts'

    @property
    def set_difference(self):
        return self.sets_for - self.sets_against

    @property
    def point_difference(self):
        return self.points_for - self.points_against
