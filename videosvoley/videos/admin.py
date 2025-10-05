from django.contrib import admin
from .models import Video, Category, League, Team, Match, ScrapingEndpoint, Standing


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'leagues_count', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at',)
    
    def leagues_count(self, obj):
        """Muestra el número de ligas asociadas"""
        return obj.leagues.count()
    leagues_count.short_description = 'Ligas'
    
    def get_search_results(self, request, queryset, search_term):
        """Mejora la búsqueda para autocomplete"""
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        return queryset, use_distinct


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'match', 'created_by', 'created_at')
    list_filter = ('category', 'match__league', 'created_at')
    search_fields = ('title', 'description', 'match__home_team__name', 'match__away_team__name')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('match',)


@admin.register(League)
class LeagueAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'federation_id', 'competition_type', 'season', 'is_active')
    list_filter = ('category', 'competition_type', 'is_active', 'season')
    search_fields = ('name', 'federation_id', 'category__name')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('category',)
    fieldsets = (
        ('Información Básica', {
            'fields': ('name', 'federation_id', 'category', 'competition_type', 'season', 'is_active')
        }),
        ('Configuración', {
            'fields': ('base_url',)
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )
    
    actions = ['scrape_selected_leagues']
    
    def scrape_selected_leagues(self, request, queryset):
        """Acción personalizada para hacer scraping de ligas seleccionadas"""
        from videosvoley.videos.scraping import FederationScraper
        
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


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'federation_id', 'created_at')
    search_fields = ('name', 'federation_id')
    readonly_fields = ('created_at',)


class ScrapingEndpointInline(admin.TabularInline):
    model = ScrapingEndpoint
    extra = 1
    fields = ('endpoint_type', 'url_pattern', 'parser_type', 'is_active')


@admin.register(ScrapingEndpoint)
class ScrapingEndpointAdmin(admin.ModelAdmin):
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


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ('home_team', 'away_team', 'match_date', 'venue', 'status', 'result_display')
    list_filter = ('status', 'league', 'match_date')
    search_fields = ('home_team__name', 'away_team__name', 'venue', 'city')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'match_date'
    fieldsets = (
        ('Partido', {
            'fields': ('league', 'home_team', 'away_team', 'match_date')
        }),
        ('Ubicación', {
            'fields': ('venue', 'city')
        }),
        ('Resultado', {
            'fields': ('status', 'home_score', 'away_score')
        }),
        ('Metadata', {
            'fields': ('round_number', 'federation_id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_search_results(self, request, queryset, search_term):
        """Mejora la búsqueda para autocomplete en VideoAdmin"""
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        return queryset, use_distinct


@admin.register(Standing)
class StandingAdmin(admin.ModelAdmin):
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