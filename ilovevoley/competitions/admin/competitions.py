from django.contrib import admin
from django.contrib.admin import helpers
from django.shortcuts import render
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline

from ilovevoley.content.admin.content import ImageInline
from ..forms import MatchAdminForm
from ..models import League, Match, MatchChangeLog, ScrapingEndpoint, Standing, Venue



@admin.register(League)
class LeagueAdmin(ModelAdmin):
    list_display = ('display_name_admin', 'categories_display', 'federation_id', 'competition_type', 'season', 'phase_indicator', 'match_format', 'visibility_type', 'is_our_team_related', 'is_historical', 'is_active', 'matches_count', 'created_at')
    list_filter = ('categories', 'competition_type', 'match_format', 'visibility_type', 'is_our_team_related', 'is_historical', 'is_active', 'season', ('parent_league', admin.RelatedOnlyFieldListFilter))
    search_fields = ('name', 'federation_id', 'categories__name')
    readonly_fields = ('created_at', 'related_organizations')
    autocomplete_fields = ('parent_league',)
    filter_horizontal = ('categories',)
    list_editable = ('visibility_type', 'is_our_team_related', 'is_historical', 'is_active')

    fieldsets = (
        ('Información Básica', {
            'fields': ('name', 'display_name_override', 'federation_id', 'categories', 'competition_type', 'season')
        }),
        ('Configuración de Fases', {
            'fields': ('parent_league', 'phase_name', 'phase_order'),
            'description': 'Configura si esta liga es una fase de otra (ej: Liguilla Oro/Plata)',
            'classes': ('collapse',)
        }),
        ('Formato de Partidos', {
            'fields': ('match_format', 'custom_max_sets', 'custom_sets_to_win'),
            'description': 'Configuración del formato de partidos y validación de resultados'
        }),
        ('Configuración de Visibilidad', {
            'fields': ('visibility_type', 'is_our_team_related', 'is_historical', 'is_active', 'related_organizations'),
            'description': 'Controla dónde y cómo se muestra la liga en la aplicación'
        }),
        ('Configuración Técnica', {
            'fields': ('base_url', 'created_at'),
            'classes': ('collapse',)
        }),
    )

    def matches_count(self, obj):
        """Muestra el número de partidos asociados"""
        return obj.matches.count()
    matches_count.short_description = 'Partidos'

    def related_organizations(self, obj):
        """Organizaciones cuyo club participa en esta liga.

        Ayuda a decidir el flag global ``is_our_team_related``: las ligas son
        datos compartidos y una liga solo interesa a los tenants cuyo club
        juega en ella (detección por FK + fallback por nombre para equipos sin
        club). El coste es constante, no depende del número de organizaciones.
        """
        if not obj or not obj.pk:
            return 'Guarda la liga para detectar organizaciones'
        from django.db.models import Q
        from ilovevoley.core.mixins import get_club_team_names
        from ilovevoley.core.models import Organization

        matches = obj.matches

        club_ids = set()
        for home_club, away_club in matches.values_list(
            'home_team__club_id', 'away_team__club_id'
        ):
            club_ids.update(cid for cid in (home_club, away_club) if cid)

        orphan_names = set()
        for home_name, home_text in matches.filter(
            Q(home_team__club__isnull=True)
        ).values_list('home_team__name', 'home_team_text'):
            orphan_names.update(name.upper() for name in (home_name, home_text) if name)
        for away_name, away_text in matches.filter(
            Q(away_team__club__isnull=True)
        ).values_list('away_team__name', 'away_team_text'):
            orphan_names.update(name.upper() for name in (away_name, away_text) if name)

        slugs = []
        for org in Organization.objects.filter(club__isnull=False):
            if org.club_id in club_ids:
                slugs.append(org.slug)
            elif any(
                name.upper() in orphan
                for name in get_club_team_names(org)
                for orphan in orphan_names
            ):
                slugs.append(org.slug)

        if not slugs:
            return format_html(
                '<span style="color:#b45309;">{}</span>',
                'Ninguna organización con club participa',
            )
        labels = ', '.join(slugs)
        if obj.is_our_team_related:
            return format_html('<span style="color:#15803d;">Participan: {}</span>', labels)
        return format_html(
            '<span style="color:#b91c1c;">Participan {} pero is_our_team_related=False</span>',
            labels,
        )
    related_organizations.short_description = 'Organizaciones con club participante'

    def display_name_admin(self, obj):
        """Muestra el nombre con indentación si es una fase"""
        if obj.parent_league:
            return f"  └─ {obj.display_name}"
        return obj.display_name
    display_name_admin.short_description = 'Nombre'

    def phase_indicator(self, obj):
        """Muestra un indicador visual si la liga tiene fases o es una fase"""
        if obj.parent_league:
            return format_html(
                '<span style="background: #f0ad4e; color: white; padding: 2px 6px; border-radius: 3px;">FASE {}</span>',
                obj.phase_order
            )
        elif obj.phases.exists():
            return format_html(
                '<span style="background: #5bc0de; color: white; padding: 2px 6px; border-radius: 3px;">{} FASES</span>',
                obj.phases.count()
            )
        return '-'
    phase_indicator.short_description = 'Fases'

    def categories_display(self, obj):
        """Muestra las categorías de forma legible"""
        cats = obj.categories.all()
        if cats:
            return ', '.join([cat.name for cat in cats])
        return '-'
    categories_display.short_description = 'Categorías'

    def get_queryset(self, request):
        """Optimiza las consultas"""
        return super().get_queryset(request).prefetch_related('matches', 'categories')

    def get_list_display(self, request):
        """Personaliza la lista según el usuario"""
        list_display = list(super().get_list_display(request))

        # Si es superusuario, mostrar todos los campos
        if request.user.is_superuser:
            return list_display

        # Para otros usuarios, ocultar algunos campos técnicos
        return [field for field in list_display if field not in ['base_url']]

    def get_list_filter(self, request):
        """Personaliza los filtros según el usuario"""
        list_filter = list(super().get_list_filter(request))

        # Agregar filtros específicos para gestión de ligas
        if request.user.is_superuser:
            list_filter.extend(['created_at'])

        return list_filter

    def get_actions(self, request):
        """Personaliza las acciones disponibles"""
        actions = super().get_actions(request)

        # Agregar acciones personalizadas para superusuarios
        if request.user.is_superuser:
            actions['mark_as_main'] = (
                self.mark_as_main,
                'mark_as_main',
                'Marcar como ligas principales'
            )
            actions['mark_as_reference'] = (
                self.mark_as_reference,
                'mark_as_reference',
                'Marcar como ligas de referencia'
            )
            actions['mark_as_historical'] = (
                self.mark_as_historical,
                'mark_as_historical',
                'Marcar como ligas históricas'
            )
            actions['mark_as_external'] = (
                self.mark_as_external,
                'mark_as_external',
                'Marcar como ligas externas'
            )

        return actions

    def mark_as_main(self, request, queryset):
        """Marca ligas como principales"""
        updated = queryset.update(
            visibility_type='main',
            is_our_team_related=True,
            is_historical=False
        )
        self.message_user(request, f'{updated} ligas marcadas como principales.')
    mark_as_main.short_description = "Marcar como ligas principales"

    def mark_as_reference(self, request, queryset):
        """Marca ligas como de referencia"""
        updated = queryset.update(
            visibility_type='reference',
            is_our_team_related=True,
            is_historical=False
        )
        self.message_user(request, f'{updated} ligas marcadas como de referencia.')
    mark_as_reference.short_description = "Marcar como ligas de referencia"

    def mark_as_historical(self, request, queryset):
        """Marca ligas como históricas"""
        updated = queryset.update(
            visibility_type='historical',
            is_historical=True,
            is_our_team_related=True
        )
        self.message_user(request, f'{updated} ligas marcadas como históricas.')
    mark_as_historical.short_description = "Marcar como ligas históricas"

    def mark_as_external(self, request, queryset):
        """Marca ligas como externas"""
        updated = queryset.update(
            visibility_type='external',
            is_our_team_related=False,
            is_historical=False
        )
        self.message_user(request, f'{updated} ligas marcadas como externas.')
    mark_as_external.short_description = "Marcar como ligas externas"

    actions = ['scrape_selected_leagues']

    def scrape_selected_leagues(self, request, queryset):
        """Acción personalizada para hacer scraping de ligas seleccionadas"""
        from ilovevoley.videos.scraping import FederationScraper

        scraped_count = 0
        error_count = 0

        for league in queryset.filter(is_active=True):
            try:
                scraper = FederationScraper(league)
                scraper.scrape_all_endpoints()
                scraped_count += 1
            except Exception as e:
                error_count += 1
                self.message_user(request, f'Error en {league.name}: {e}', level='ERROR')

        if scraped_count > 0:
            self.message_user(request, f'Scraping completado para {scraped_count} liga(s)')
        if error_count > 0:
            self.message_user(request, f'{error_count} liga(s) con errores', level='WARNING')

    scrape_selected_leagues.short_description = "Hacer scraping de ligas seleccionadas"


class ScrapingEndpointInline(TabularInline):
    model = ScrapingEndpoint
    extra = 1
    fields = ('endpoint_type', 'url_pattern', 'parser_type', 'is_active')


@admin.register(ScrapingEndpoint)
class ScrapingEndpointAdmin(ModelAdmin):
    list_display = ('league', 'endpoint_type', 'parser_type', 'is_active')
    list_filter = ('endpoint_type', 'parser_type', 'is_active')
    search_fields = ('league__name', 'url_pattern')
    readonly_fields = ('created_at',)
    fieldsets = (
        ('Configuración', {
            'fields': ('league', 'endpoint_type', 'parser_type', 'is_active')
        }),
        ('URL', {
            'fields': ('url_pattern',),
            'description': 'Usar {league_id}, {round}, etc. para parámetros dinámicos'
        }),
        ('Parámetros Adicionales', {
            'fields': ('extra_params',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )


@admin.register(Venue)
class VenueAdmin(ModelAdmin):
    list_display = ('name', 'city', 'address', 'google_maps_url_link', 'is_active')
    list_filter = ('city', 'is_active')
    search_fields = ('name', 'city', 'aliases', 'address')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Identificación', {
            'fields': ('name', 'short_name', 'is_active')
        }),
        ('Ubicación Física', {
            'fields': ('address', 'city', 'postal_code', 'latitude', 'longitude')
        }),
        ('Navegación y Maps', {
            'fields': ('google_maps_url',)
        }),
        ('Scraping y Alias', {
            'fields': ('aliases',),
            'description': 'Alias o variantes de nombre separadas por coma usadas en actas/scraping'
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def google_maps_url_link(self, obj):
        if obj.google_maps_url:
            return format_html('<a href="{}" target="_blank">Ver mapa</a>', obj.google_maps_url)
        return '-'
    google_maps_url_link.short_description = 'Google Maps'


@admin.register(Match)
class MatchAdmin(ModelAdmin):
    form = MatchAdminForm
    list_display = ('__str__', 'match_date', 'venue', 'status', 'result_display', 'league_categories', 'match_type_display', 'teams_active_status', 'referee_display')
    list_filter = ('is_friendly', 'status', 'league', 'league__categories', 'match_date', 'home_team__is_active', 'away_team__is_active', 'referee1', 'scorer')
    search_fields = ('home_team__name', 'away_team__name', 'venue', 'city', 'league__name', 'referee1', 'referee2', 'scorer', 'timekeeper', 'delegate', 'field_address')
    readonly_fields = ('created_at', 'updated_at', 'set_scores')
    autocomplete_fields = ('venue_ref',)
    date_hierarchy = 'match_date'
    inlines = [ImageInline]
    actions = ['mark_as_withdrawn', 'mark_as_scheduled']

    def get_queryset(self, request):
        """Usar all_objects en el admin para ver todos los partidos, incluyendo withdrawn"""
        return Match.all_objects.get_queryset()

    fieldsets = (
        ('Configuración de Filtrado', {
            'fields': ('filter_by_category',),
            'description': 'Controla qué equipos se muestran en los campos de selección'
        }),
        ('Tipo de Partido', {
            'fields': ('is_friendly',),
            'description': 'Marca como amistoso si se crea manualmente'
        }),
        ('Partido', {
            'fields': ('league', 'home_team', 'home_team_text', 'away_team', 'away_team_text', 'match_date'),
            'description': 'Para partidos amistosos, puedes usar campos de texto si el equipo no existe en BD'
        }),
        ('Ubicación', {
            'fields': ('venue_ref', 'venue', 'city', 'field_address')
        }),
        ('Resultado', {
            'fields': ('status', 'home_score', 'away_score', 'set_scores', 'result_penalized')
        }),
        ('Personal Oficial', {
            'fields': ('referee1', 'referee2', 'scorer', 'timekeeper', 'delegate'),
            'classes': ('collapse',),
            'description': 'Personal técnico del partido (se llena automáticamente desde la federación)'
        }),
        ('Datos de la Federación', {
            'fields': ('federation_id', 'federation_club_local_id', 'federation_club_away_id', 'acta_html'),
            'classes': ('collapse',),
            'description': 'IDs y enlaces de la federación (se llenan automáticamente)'
        }),
        ('Metadata', {
            'fields': ('round_number', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    class Media:
        js = ('admin/js/match_admin.js',)

    def league_categories(self, obj):
        """Muestra las categorías de la liga"""
        if not obj.league:
            return '-'
        cats = obj.league.categories.all()
        if cats:
            return ', '.join([cat.name for cat in cats])
        return '-'
    league_categories.short_description = 'Categorías'

    def match_type_display(self, obj):
        """Muestra el tipo de partido"""
        if obj.is_friendly:
            return '🏐 Amistoso'
        elif obj.federation_id:
            return '🏆 Oficial'
        return '❓ Otro'
    match_type_display.short_description = 'Tipo'

    def teams_active_status(self, obj):
        """Muestra el estado activo de los equipos"""
        # Para partidos amistosos con texto, no hay estado
        if not obj.home_team or not obj.away_team:
            return '-'

        home_status = "✓" if obj.home_team.is_active else "✗"
        away_status = "✓" if obj.away_team.is_active else "✗"

        if not obj.home_team.is_active or not obj.away_team.is_active:
            return format_html(
                '<span style="color: red;">{} / {}</span>',
                home_status, away_status
            )
        else:
            return format_html(
                '<span style="color: green;">{} / {}</span>',
                home_status, away_status
            )
    teams_active_status.short_description = 'Equipos Activos (L/V)'

    def referee_display(self, obj):
        """Muestra información de árbitros"""
        referees = []
        if obj.referee1:
            referees.append(f"1: {obj.referee1}")
        if obj.referee2:
            referees.append(f"2: {obj.referee2}")

        if referees:
            return format_html(
                '<div style="font-size: 11px; line-height: 1.2;">{}</div>',
                '<br>'.join(referees)
            )
        return '-'
    referee_display.short_description = 'Árbitros'

    def get_search_results(self, request, queryset, search_term):
        """Mejora la búsqueda para autocomplete en VideoAdmin"""
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        return queryset, use_distinct

    def mark_as_withdrawn(self, request, queryset):
        """Acción para marcar partidos como retirados"""
        updated = queryset.filter(status__in=['scheduled', 'postponed']).update(status='withdrawn')
        if updated:
            self.message_user(request, f'{updated} partido(s) marcado(s) como retirado(s).')
        else:
            self.message_user(request, 'No se pueden marcar como retirados partidos que ya están finalizados o en progreso.')
    mark_as_withdrawn.short_description = "Marcar como retirados (equipos fuera de liga)"

    def mark_as_scheduled(self, request, queryset):
        """Acción para reactivar partidos marcados como retirados"""
        updated = queryset.filter(status='withdrawn').update(status='scheduled')
        if updated:
            self.message_user(request, f'{updated} partido(s) reactivado(s) como programado(s).')
        else:
            self.message_user(request, 'No hay partidos retirados seleccionados para reactivar.')
    mark_as_scheduled.short_description = "Reactivar partidos retirados como programados"


@admin.register(Standing)
class StandingAdmin(ModelAdmin):
    list_display = ('position', 'team', 'league', 'total_points', 'played', 'won', 'lost')
    list_filter = ('league',)
    search_fields = ('team__name', 'league__name')
    readonly_fields = ('updated_at', 'set_difference', 'point_difference')
    ordering = ('league', 'position')
    fieldsets = (
        ('Posición', {
            'fields': ('league', 'team', 'position')
        }),
        ('Estadísticas Generales', {
            'fields': ('played', 'won', 'lost', 'total_points')
        }),
        ('Sets y Puntos', {
            'fields': ('sets_for', 'sets_against', 'points_for', 'points_against')
        }),
        ('Detalles Victorias/Derrotas', {
            'fields': ('wins_3_0', 'wins_3_1', 'wins_3_2', 'losses_2_3', 'losses_1_3', 'losses_0_3'),
            'classes': ('collapse',)
        }),
        ('Calculados', {
            'fields': ('set_difference', 'point_difference', 'updated_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(MatchChangeLog)
class MatchChangeLogAdmin(ModelAdmin):
    list_display = (
        'match', 'change_type_badge', 'field_name', 'old_value', 'new_value',
        'is_last_minute', 'notified', 'reviewed', 'detected_at'
    )
    list_filter = ('change_type', 'is_last_minute', 'notified', 'reviewed', 'detected_at')
    search_fields = ('match__home_team__name', 'match__away_team__name', 'field_name', 'old_value', 'new_value')
    readonly_fields = ('detected_at', 'notified_at', 'reviewed_at')
    actions = ['mark_as_reviewed']
    list_select_related = ('match__home_team', 'match__away_team', 'reviewed_by')

    def change_type_badge(self, obj):
        colors = {
            'datetime': 'background: #fee2e2; color: #991b1b;',
            'venue': 'background: #fef3c7; color: #92400e;',
            'status': 'background: #f3e8ff; color: #6b21a8;',
            'score': 'background: #dbeafe; color: #1e40af;',
            'other': 'background: #f3f4f6; color: #374151;',
        }
        style = colors.get(obj.change_type, colors['other'])
        return format_html(
            '<span style="padding: 2px 8px; border-radius: 4px; font-weight: 500; font-size: 11px; {}">{}</span>',
            style,
            obj.get_change_type_display(),
        )
    change_type_badge.short_description = 'Tipo'

    def mark_as_reviewed(self, request, queryset):
        """Marca las modificaciones seleccionadas como revisadas."""
        now = timezone.now()
        updated = queryset.update(reviewed=True, reviewed_by=request.user, reviewed_at=now)
        self.message_user(request, f'{updated} modificación(es) marcada(s) como revisada(s).')
    mark_as_reviewed.short_description = "Marcar modificaciones seleccionadas como revisadas"

