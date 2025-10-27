from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import League, Match, Standing, ScrapingEndpoint


@admin.register(League)
class LeagueAdmin(admin.ModelAdmin):
    list_display = ['name', 'season', 'competition_type', 'visibility_type', 'is_active', 'is_our_team_related', 'created_at']
    list_filter = ['competition_type', 'visibility_type', 'is_active', 'is_historical', 'is_our_team_related', 'created_at']
    search_fields = ['name', 'federation_id', 'season']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('name', 'federation_id', 'competition_type', 'season', 'category')
        }),
        ('Configuración de Visibilidad', {
            'fields': ('visibility_type', 'is_active', 'is_historical', 'is_our_team_related'),
            'classes': ('collapse',)
        }),
        ('Formato de Partidos', {
            'fields': ('match_format', 'custom_max_sets', 'custom_sets_to_win'),
            'classes': ('collapse',)
        }),
        ('Configuración Técnica', {
            'fields': ('base_url', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['make_main_league', 'make_reference_league', 'activate_leagues', 'deactivate_leagues']
    
    def make_main_league(self, request, queryset):
        updated = queryset.update(visibility_type='main', is_active=True, is_our_team_related=True)
        self.message_user(request, f'{updated} ligas marcadas como principales.')
    make_main_league.short_description = 'Marcar como liga principal'
    
    def make_reference_league(self, request, queryset):
        updated = queryset.update(visibility_type='reference', is_our_team_related=False)
        self.message_user(request, f'{updated} ligas marcadas como referencia.')
    make_reference_league.short_description = 'Marcar como liga de referencia'
    
    def activate_leagues(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} ligas activadas.')
    activate_leagues.short_description = 'Activar ligas seleccionadas'
    
    def deactivate_leagues(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} ligas desactivadas.')
    deactivate_leagues.short_description = 'Desactivar ligas seleccionadas'


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ['home_team_display', 'away_team_display', 'league', 'match_date', 'status', 'result_display', 'is_friendly']
    list_filter = ['status', 'is_friendly', 'league', 'match_date', 'created_at']
    search_fields = ['home_team_text', 'away_team_text', 'venue', 'city', 'federation_id']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-match_date']
    
    fieldsets = (
        ('Información del Partido', {
            'fields': ('league', 'match_date', 'venue', 'city', 'round_number', 'status')
        }),
        ('Equipos', {
            'fields': ('home_team', 'home_team_text', 'away_team', 'away_team_text', 'is_friendly')
        }),
        ('Resultado', {
            'fields': ('home_score', 'away_score'),
            'classes': ('collapse',)
        }),
        ('Información Técnica', {
            'fields': ('referee1', 'referee2', 'scorer', 'timekeeper', 'delegate'),
            'classes': ('collapse',)
        }),
        ('Información del Campo', {
            'fields': ('field_address', 'federation_club_local_id', 'federation_club_away_id'),
            'classes': ('collapse',)
        }),
        ('Acta Oficial', {
            'fields': ('acta_html', 'federation_id'),
            'classes': ('collapse',)
        }),
        ('Metadatos', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['mark_as_finished', 'mark_as_postponed', 'mark_as_cancelled']
    
    def mark_as_finished(self, request, queryset):
        updated = queryset.update(status='finished')
        self.message_user(request, f'{updated} partidos marcados como finalizados.')
    mark_as_finished.short_description = 'Marcar como finalizados'
    
    def mark_as_postponed(self, request, queryset):
        updated = queryset.update(status='postponed')
        self.message_user(request, f'{updated} partidos marcados como aplazados.')
    mark_as_postponed.short_description = 'Marcar como aplazados'
    
    def mark_as_cancelled(self, request, queryset):
        updated = queryset.update(status='cancelled')
        self.message_user(request, f'{updated} partidos marcados como cancelados.')
    mark_as_cancelled.short_description = 'Marcar como cancelados'


@admin.register(Standing)
class StandingAdmin(admin.ModelAdmin):
    list_display = ['position', 'team', 'league', 'played', 'won', 'lost', 'total_points', 'set_difference', 'win_percentage']
    list_filter = ['league', 'updated_at']
    search_fields = ['team__name', 'league__name']
    readonly_fields = ['updated_at']
    ordering = ['league', 'position']
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('league', 'team', 'position')
        }),
        ('Estadísticas de Partidos', {
            'fields': ('played', 'won', 'lost')
        }),
        ('Estadísticas de Sets', {
            'fields': ('sets_for', 'sets_against', 'set_difference')
        }),
        ('Estadísticas de Puntos', {
            'fields': ('points_for', 'points_against', 'point_difference')
        }),
        ('Desglose de Resultados', {
            'fields': ('wins_3_0', 'wins_3_1', 'wins_3_2', 'losses_2_3', 'losses_1_3', 'losses_0_3'),
            'classes': ('collapse',)
        }),
        ('Metadatos', {
            'fields': ('total_points', 'win_percentage', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def set_difference(self, obj):
        return obj.set_difference
    set_difference.short_description = 'Dif. Sets'
    
    def point_difference(self, obj):
        return obj.point_difference
    point_difference.short_description = 'Dif. Puntos'
    
    def win_percentage(self, obj):
        return f"{obj.win_percentage}%"
    win_percentage.short_description = '% Victorias'


@admin.register(ScrapingEndpoint)
class ScrapingEndpointAdmin(admin.ModelAdmin):
    list_display = ['league', 'endpoint_type', 'parser_type', 'is_active', 'created_at']
    list_filter = ['endpoint_type', 'parser_type', 'is_active', 'created_at']
    search_fields = ['league__name', 'url_pattern']
    readonly_fields = ['created_at']
    ordering = ['league', 'endpoint_type']
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('league', 'endpoint_type', 'parser_type', 'is_active')
        }),
        ('Configuración de URL', {
            'fields': ('url_pattern', 'extra_params'),
            'classes': ('collapse',)
        }),
        ('Metadatos', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['activate_endpoints', 'deactivate_endpoints']
    
    def activate_endpoints(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} endpoints activados.')
    activate_endpoints.short_description = 'Activar endpoints seleccionados'
    
    def deactivate_endpoints(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} endpoints desactivados.')
    deactivate_endpoints.short_description = 'Desactivar endpoints seleccionados'